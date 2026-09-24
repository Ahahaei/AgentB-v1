"""Stage 4a — the worker claim loop, exercised while still dormant.

These run against SQLite, so they cover the compare-and-swap claim path. The
Postgres path (`FOR UPDATE SKIP LOCKED`) is structurally different and is NOT
covered here — see the note in worker.py.
"""
from datetime import datetime, timedelta, timezone

import pytest

import worker
from app import store
from app.db.engine import SessionLocal
from app.db.models import JobRow
from app.models.event import EventStatus, EventType
from app.models.job import JobStatus


@pytest.fixture(autouse=True)
def eager_worker():
    """Override conftest's eager drain — this file drives the worker by hand."""
    yield


def enqueue(seller_id="S001", sku="WIDGET-42"):
    """An event + pending job, without running anything."""
    return store.ingest_internal_event(
        seller_id,
        EventType.INVENTORY_LOW,
        {"sku": sku, "current_quantity": 3},
    )


def patch_job(job_id, **fields):
    db = SessionLocal()
    try:
        row = db.get(JobRow, job_id)
        for key, value in fields.items():
            setattr(row, key, value)
        db.commit()
    finally:
        db.close()


def now():
    return datetime.now(timezone.utc)


# --- claiming ---

def test_empty_queue_claims_nothing():
    assert store.claim_job() is None


def test_claim_marks_processing_and_counts_the_attempt():
    enqueued = enqueue()
    job = store.claim_job()
    assert job is not None
    assert job.id == enqueued.job_id
    assert job.status == JobStatus.PROCESSING
    assert job.attempts == 1
    assert job.locked_at is not None


def test_a_claimed_job_is_not_claimed_again():
    enqueue()
    assert store.claim_job() is not None
    assert store.claim_job() is None


def test_job_scheduled_for_later_is_not_due():
    enqueued = enqueue()
    patch_job(enqueued.job_id, run_after=now() + timedelta(hours=1))
    assert store.claim_job() is None


def test_oldest_job_is_claimed_first():
    first = enqueue(sku="FIRST")
    second = enqueue(sku="SECOND")
    patch_job(second.job_id, created_at=now() + timedelta(minutes=5))
    assert store.claim_job().id == first.job_id


# --- the reaper arm ---

def test_stale_processing_job_is_reclaimed():
    enqueued = enqueue()
    patch_job(
        enqueued.job_id,
        status=JobStatus.PROCESSING.value,
        locked_at=now() - timedelta(minutes=30),
        attempts=1,
    )
    job = store.claim_job(stale_after_seconds=300)
    assert job is not None
    assert job.attempts == 2          # the abandoned attempt still counted


def test_freshly_locked_job_is_left_alone():
    enqueued = enqueue()
    patch_job(
        enqueued.job_id,
        status=JobStatus.PROCESSING.value,
        locked_at=now() - timedelta(seconds=5),
    )
    assert store.claim_job(stale_after_seconds=300) is None


# --- processing ---

def test_run_once_processes_and_closes_the_job():
    enqueued = enqueue()
    assert worker.run_once() is True
    assert store.get_job(enqueued.job_id).status == JobStatus.DONE
    assert store.get_event(enqueued.event_id).status == EventStatus.COMPLETED


def test_run_once_on_an_empty_queue_reports_nothing_done():
    assert worker.run_once() is False


def test_failed_pipeline_is_rescheduled_with_backoff():
    enqueued = enqueue(seller_id="S003")     # inactive seller → pipeline fails
    worker.run_once()

    job = store.get_job(enqueued.job_id)
    assert job.status == JobStatus.PENDING
    assert job.attempts == 1
    assert job.locked_at is None
    assert job.run_after > now()
    assert "not active" in job.last_error


def test_failure_is_dead_lettered_once_attempts_are_spent():
    enqueued = enqueue(seller_id="S003")
    patch_job(enqueued.job_id, attempts=worker.MAX_ATTEMPTS - 1)
    worker.run_once()

    job = store.get_job(enqueued.job_id)
    assert job.status == JobStatus.DEAD
    assert job.attempts == worker.MAX_ATTEMPTS


def test_a_job_that_never_reaches_fail_is_still_dead_lettered():
    """A worker that dies mid-job never runs _fail, so the cap there never fires.

    Simulated by leaving the job in `processing` with a stale lock and an
    attempts count already past budget — exactly the state a crash-looping job
    reaches after the reaper has handed it back enough times.
    """
    enqueued = enqueue()
    patch_job(
        enqueued.job_id,
        status=JobStatus.PROCESSING.value,
        locked_at=now() - timedelta(minutes=30),
        attempts=worker.MAX_ATTEMPTS,        # claim will make it MAX_ATTEMPTS + 1
    )

    assert worker.run_once() is True
    job = store.get_job(enqueued.job_id)
    assert job.status == JobStatus.DEAD
    assert "without completing" in job.last_error
    # and the event was never touched — the pipeline did not get to run again
    assert store.get_event(enqueued.event_id).status == EventStatus.PENDING


def test_crash_loop_is_bounded():
    """Repeated reclaims of a job nothing ever completes terminate."""
    enqueued = enqueue()
    for _ in range(worker.MAX_ATTEMPTS + 2):
        job = store.get_job(enqueued.job_id)
        if job.status == JobStatus.DEAD:
            break
        # simulate a worker that claimed it and died: stale lock, no _fail
        patch_job(
            enqueued.job_id,
            status=JobStatus.PROCESSING.value,
            locked_at=now() - timedelta(minutes=30),
        )
        worker.run_once()

    assert store.get_job(enqueued.job_id).status == JobStatus.DEAD


def test_backoff_grows_and_is_capped():
    assert worker.backoff_seconds(1) == 5
    assert worker.backoff_seconds(2) == 10
    assert worker.backoff_seconds(3) == 20
    assert worker.backoff_seconds(99) == worker.MAX_BACKOFF_SECONDS


# --- drain ---

def test_drain_processes_everything_due():
    jobs = [enqueue(sku=f"SKU-{i}") for i in range(3)]
    assert worker.drain() == 3
    assert all(store.get_job(j.job_id).status == JobStatus.DONE for j in jobs)


def test_drain_terminates_when_a_job_reschedules_itself():
    # The retry's run_after is in the future, so drain does not spin on it.
    enqueue(seller_id="S003")
    assert worker.drain(max_jobs=10) == 1
