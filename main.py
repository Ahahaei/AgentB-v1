from fastapi import FastAPI

from app.routers.approvals import router as approvals_router
from app.routers.events import router as events_router
from app.routers.webhooks import router as webhooks_router

app = FastAPI()
app.include_router(events_router)
app.include_router(webhooks_router)
app.include_router(approvals_router)


@app.get("/")
def root():
    return {"message": "Hello, World!"}


@app.get("/health")
def health():
    return {"status": "ok"}
