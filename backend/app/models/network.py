"""SQLAlchemy tables describing the baseline bus network."""

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Stop(Base):
    """A bus stop. Becomes a node in the network graph."""

    __tablename__ = "stops"

    # Short readable code (e.g. "CEN") so scenarios and AI output can
    # reference stops without opaque numeric ids.
    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)


class Route(Base):
    """A bus line. Groups the connections it serves."""

    __tablename__ = "routes"

    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    color: Mapped[str] = mapped_column(String(7))  # hex colour for the map


class Connection(Base):
    """A directed link between two consecutive stops on one route.

    A two-way street is stored as two rows (A->B and B->A).
    """

    __tablename__ = "connections"
    __table_args__ = (
        UniqueConstraint("route_id", "from_stop_id", "to_stop_id"),
        CheckConstraint("travel_time_min > 0", name="positive_travel_time"),
        CheckConstraint("from_stop_id <> to_stop_id", name="no_self_loop"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    route_id: Mapped[str] = mapped_column(ForeignKey("routes.id"))
    from_stop_id: Mapped[str] = mapped_column(ForeignKey("stops.id"))
    to_stop_id: Mapped[str] = mapped_column(ForeignKey("stops.id"))
    travel_time_min: Mapped[float] = mapped_column(Float)
