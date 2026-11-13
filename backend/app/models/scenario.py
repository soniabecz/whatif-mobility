"""SQLAlchemy table for scenarios saved by the user (Day 13).

Only the change list is stored, never results: they are recomputed from the
current network every time, so a saved result can never go stale.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class SavedScenario(Base):
    __tablename__ = "saved_scenarios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    # The change list in the scenario format (JSON), validated on write and read.
    changes_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
