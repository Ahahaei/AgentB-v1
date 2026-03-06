import os

import pytest

# Pin Slack off before any test file imports main.py and triggers load_dotenv().
# load_dotenv() defaults to override=False, so this value wins.
os.environ["SLACK_ENABLED"] = "false"

from app import store


@pytest.fixture(autouse=True)
def clear_event_store():
    store._events.clear()
    store._approvals.clear()
    yield
    store._events.clear()
    store._approvals.clear()
