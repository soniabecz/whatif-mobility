"""SQLAlchemy engine, session factory and declarative base.

The SQLite database file lives in backend/ (git-ignored): ``gdansk.db`` by
default (the Gdańsk network, the app's only network), or the file named by the
WHATIF_DATABASE environment variable. The invented sample city exists only as
test data: its databases are named ``e2e-*.db`` (see app/seed).

    python -m app.import_gtfs                              # Gdańsk trams and buses
    WHATIF_DATABASE=e2e-sample.db python -m app.seed       # browser tests only
"""

import os
import re

from collections.abc import Iterator
from pathlib import Path
from sqlite3 import Connection as SQLiteConnection
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent.parent


DEFAULT_DATABASE = "gdansk.db"
# The sample seed writes only into databases named like this (test data).
TEST_DATABASE_PREFIX = "e2e-"


def database_file(name: str | None = None) -> Path:
    """The database file in backend/: a plain file name ending in .db."""
    name = name or os.environ.get("WHATIF_DATABASE") or DEFAULT_DATABASE
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.db", name):
        raise ValueError(f"WHATIF_DATABASE must be a file name like gdansk.db, not {name!r}")
    return BACKEND_DIR / name


DATABASE_URL = f"sqlite:///{database_file()}"


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    """SQLite ignores foreign keys unless this is switched on per connection."""
    if isinstance(dbapi_connection, SQLiteConnection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# check_same_thread=False: FastAPI may use a session from a different thread
# than the one that created the connection. Each request still gets its own
# session (see get_db), so this is safe.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one database session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
