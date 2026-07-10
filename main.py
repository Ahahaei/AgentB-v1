import logging
import os

from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault("DATABASE_URL", "")

from contextlib import asynccontextmanager

from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

from app.routers.approvals import router as approvals_router
from app.routers.events import router as events_router
from app.routers.oauth import router as oauth_router
from app.routers.sellers import router as sellers_router
from app.routers.slack import router as slack_router
from app.routers.slack_oauth import router as slack_oauth_router
from app.routers.webhooks import router as webhooks_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from alembic.config import Config
    from alembic import command
    from app.db.seed import seed_sellers
    os.environ["RUNNING_IN_APP"] = "1"
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    seed_sellers()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(events_router)
app.include_router(webhooks_router)
app.include_router(approvals_router)
app.include_router(sellers_router)
app.include_router(oauth_router)
app.include_router(slack_router)
app.include_router(slack_oauth_router)


@app.get("/")
def root():
    return {"message": "Hello, World!"}


@app.get("/health")
def health():
    return {"status": "ok"}
