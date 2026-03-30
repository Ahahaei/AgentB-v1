import os

# Must be set before any app imports trigger engine creation.
os.environ["SLACK_ENABLED"] = "false"
os.environ["SP_API_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from sqlalchemy import text

from app.db.engine import SessionLocal, create_tables
from app.db.seed import seed_sellers


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    create_tables()
    seed_sellers()


@pytest.fixture(autouse=True)
def clear_tables():
    yield
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM approvals"))
        db.execute(text("DELETE FROM events"))
        db.commit()
    finally:
        db.close()
