import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


_DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not _DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

_is_sqlite = _DATABASE_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}
_pool_kwargs = {"poolclass": StaticPool} if _is_sqlite else {}

engine = create_engine(_DATABASE_URL, connect_args=_connect_args, **_pool_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def create_tables() -> None:
    from app.db import models  # noqa — registers all ORM classes with Base.metadata
    Base.metadata.create_all(engine)
