"""Job queue worker.

    python worker.py

This is the only thing that processes events. The API writes an event and a job
and returns; nothing happens until a worker claims the job. Run at least one.

Mirrors main.py's entrypoint discipline: `DATABASE_URL` must be resolved before
anything under `app/` is imported, because `app.db.engine` creates the engine at
import time.
"""
import logging
import os
import signal
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault("DATABASE_URL", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("worker")

from app import store
from app.engine.pipeline import run_pipeline
from app.models.event import EventStatus
from app.models.job import Job, JobStatus

# A job is retried this many times in total before it is dead-lettered.
MAX_ATTEMPTS = 5
# Backoff doubles per attempt from here, capped, so a failing platform is not
# hammered: 5s, 10s, 20s, 40s.
BASE_BACKOFF_SECONDS = 5
MAX_BACKOFF_SECONDS = 300
# How long a `processing` row may sit before the claim treats it as abandoned.
STALE_AFTER_SECONDS = 300
# Sleep when the queue is empty. Postgres LISTEN/NOTIFY would remove this.
IDLE_SLEEP_SECONDS = 1.0

_shutdown = False


def backoff_seconds(attempts: int) -> int:
    return min(BASE_BACKOFF_SECONDS * 2 ** max(attempts - 1, 0), MAX_BACKOFF_SECONDS)


def _fail(job: Job, error: Optional[str]) -> None:
    """Retry with backoff, or dead-letter once the attempts are spent.

    Everything is treated as retryable for now. Telling a retryable failure from
    a terminal one is `adapter.classify_error`'s job, and that arrives with the
    write half — so a permanently broken job burns its attempts before landing
    in `dead` rather than going there immediately.
    """
    if job.attempts >= MAX_ATTEMPTS:
        logger.error("job=%s dead after %s attempts: %s", job.id, job.attempts, error)
        store.finish_job(job.id, JobStatus.DEAD, error=error)
        return

    delay = backoff_seconds(job.attempts)
    logger.warning(
        "job=%s attempt %s/%s failed, retrying in %ss: %s",
        job.id, job.attempts, MAX_ATTEMPTS, delay, error,
    )
    store.reschedule_job(
        job.id,
        run_after=datetime.now(timezone.utc) + timedelta(seconds=delay),
        error=error,
    )


def run_once() -> bool:
    """Claim and process one job. False means the queue had nothing due."""
    job = store.claim_job(stale_after_seconds=STALE_AFTER_SECONDS)
    if job is None:
        return False

    # Budget check at claim time, not only in _fail. A job that kills its worker
    # — OOM, eviction, a segfaulting dependency — never reaches _fail, so the
    # cap there never fires: the reaper keeps handing it back and `attempts`
    # climbs forever. Checking here bounds it whether or not anything survives
    # to report the failure, and does it *before* run_pipeline can bite again.
    if job.attempts > MAX_ATTEMPTS:
        logger.error(
            "job=%s abandoned after %s pickups without completing — dead", job.id, job.attempts
        )
        store.finish_job(
            job.id,
            JobStatus.DEAD,
            error=f"claimed {job.attempts} times without completing",
        )
        return True

    logger.info("job=%s claimed event=%s attempt=%s", job.id, job.event_id, job.attempts)
    try:
        run_pipeline(job.event_id)
    except Exception as exc:  # run_pipeline handles its own errors; this is a backstop
        logger.exception("job=%s raised out of the pipeline", job.id)
        _fail(job, str(exc))
        return True

    event = store.get_event(job.event_id)
    if event is not None and event.status == EventStatus.FAILED:
        _fail(job, event.error)
    else:
        store.finish_job(job.id, JobStatus.DONE)
    return True


def drain(max_jobs: int = 1000) -> int:
    """Process everything currently due, then stop. Used by tests and one-shots.

    Terminates because a rescheduled job's `run_after` is in the future, so it is
    not claimable again on this pass.
    """
    processed = 0
    while processed < max_jobs and run_once():
        processed += 1
    return processed


def _request_shutdown(signum, _frame) -> None:
    global _shutdown
    logger.info("signal %s received — finishing current job then exiting", signum)
    _shutdown = True


def main() -> None:
    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)

    logger.info("worker started (max_attempts=%s, stale_after=%ss)", MAX_ATTEMPTS, STALE_AFTER_SECONDS)
    while not _shutdown:
        try:
            if not run_once():
                time.sleep(IDLE_SLEEP_SECONDS)
        except Exception:
            # Never let one bad iteration kill the loop.
            logger.exception("worker iteration failed")
            time.sleep(IDLE_SLEEP_SECONDS)
    logger.info("worker stopped")


if __name__ == "__main__":
    main()
