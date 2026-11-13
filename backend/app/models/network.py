"""SQLAlchemy tables describing the baseline bus network."""

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Stop(Base):
    """A bus stop. Becomes a node in the network graph."""

    __tablename__ = "stops"
    __table_args__ = (CheckConstraint("activity BETWEEN 1 AND 3", name="activity_level"),)

    # Short readable code (e.g. "CEN") so scenarios and AI output can
    # reference stops without opaque numeric ids.
    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    # INVENTED activity level (1 quiet, 2 medium, 3 major) for demand
    # weighting: a journey weighs origin level x destination level.
    activity: Mapped[int] = mapped_column(Integer, default=1)


class Route(Base):
    """A bus line. Groups the connections it serves."""

    __tablename__ = "routes"
    __table_args__ = (CheckConstraint("headway_min > 0", name="positive_headway"),)

    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    color: Mapped[str] = mapped_column(String(7))  # hex colour for the map
    # Minutes between two buses (invented for the sample network). Passengers
    # arriving at random wait half of it on average.
    headway_min: Mapped[float] = mapped_column(Float)


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


class NetworkSource(Base):
    """Where a real network comes from (one row; none for the invented sample).

    Shown in the app: the data's terms require naming the publisher and the
    dates the data was created and downloaded.
    """

    __tablename__ = "network_source"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))  # e.g. "Gdańsk – trams"
    publisher: Mapped[str] = mapped_column(String(200))
    attribution_url: Mapped[str] = mapped_column(String(300))
    licence: Mapped[str] = mapped_column(String(300))
    feed_url: Mapped[str] = mapped_column(String(500))
    feed_created: Mapped[str] = mapped_column(String(10))  # ISO date of the feed's files
    downloaded: Mapped[str] = mapped_column(String(10))  # ISO date
    reference_date: Mapped[str] = mapped_column(String(10))  # the weekday the network is built from
    # How the network was derived (shown on request): grouping, times, headways.
    method: Mapped[str] = mapped_column(Text)
