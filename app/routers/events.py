import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app import store
from app.engine.pipeline import run_pipeline
from app.models.event import EventInput, EventRecord, EventStatus

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", status_code=202)
def ingest_event(event: EventInput, background_tasks: BackgroundTasks):
    event_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    record = EventRecord(
        id=event_id,
        seller_id=event.seller_id,
        event_type=event.event_type,
        payload=event.payload,
        status=EventStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    store.create_event(record)
    background_tasks.add_task(run_pipeline, event_id)
    return {"event_id": event_id, "status": EventStatus.PENDING}


@router.get("/{event_id}")
def get_event(event_id: str):
    record = store.get_event(event_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")
    return record
