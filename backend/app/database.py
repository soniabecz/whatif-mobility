"""SQLAlchemy engine, session factory and declarative base.

The SQLite database file lives at ``backend/whatif.db`` (git-ignored).
It is (re)created from the sample data with:

    python -m app.seed
"""

from collections.abc import Iterator
from pathlib import Path
from sqlite3 import Connection as SQLiteConnection
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = f"sqlite:///{BACKEND_DIR / 'whatif.db'}"


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
