from fastapi import FastAPI

from app.routers.events import router as events_router

app = FastAPI()
app.include_router(events_router)


@app.get("/")
def root():
    return {"message": "Hello, World!"}


@app.get("/health")
def health():
    return {"status": "ok"}
