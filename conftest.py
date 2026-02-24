import pytest

from app import store


@pytest.fixture(autouse=True)
def clear_event_store():
    store._events.clear()
    yield
    store._events.clear()
