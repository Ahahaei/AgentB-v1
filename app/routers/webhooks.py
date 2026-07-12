import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app import store
from app.engine.pipeline import run_pipeline
from app.models.event import DOMAIN_EVENT_TYPES, EventInput, EventRecord, EventStatus

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/sp-api", status_code=202)
def receive_sp_api_event(event: EventInput, background_tasks: BackgroundTasks):
    if event.event_type not in DOMAIN_EVENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"'{event.event_type}' is not a domain event. Use POST /events for monitoring events.",
        )
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
