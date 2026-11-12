"""Load the sample network into the database."""

from sqlalchemy import delete, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.database import Base

from app.models import Connection, Route, Stop
from app.seed.sample_network import ROUTES, STOPS, route_segments, stop_coordinates


def schema_is_current(engine: Engine) -> bool:
    """False when an existing table's columns differ from the models.

    There are no migrations: the database holds only generated sample data,
    so an outdated database is simply rebuilt (see app/seed/__main__.py).
    Missing tables are fine; ``create_all`` adds them.
    """
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        if existing != {column.name for column in table.columns}:
            return False
    return True


def network_is_empty(db: Session) -> bool:
    """True when no stops are stored yet (fresh or never-seeded database)."""
    return db.scalar(select(Stop.id).limit(1)) is None


def seed_database(db: Session) -> None:
    """Replace all network data with the sample network (idempotent).

    Runs in one transaction: either the whole network is written or nothing.
    """
    try:
        db.execute(delete(Connection))
        db.execute(delete(Route))
        db.execute(delete(Stop))

        for s in STOPS:
            lat, lon = stop_coordinates(s)
            db.add(Stop(id=s.id, name=s.name, lat=lat, lon=lon))
        for r in ROUTES:
            db.add(Route(id=r.id, name=r.name, color=r.color, headway_min=r.headway_min))
        db.flush()  # stops and routes must exist before connections (FKs)

        for r in ROUTES:
            for from_id, to_id, minutes in route_segments(r):
                db.add(
                    Connection(
                        route_id=r.id,
                        from_stop_id=from_id,
                        to_stop_id=to_id,
                        travel_time_min=minutes,
                    )
                )
        db.commit()
    except Exception:
        db.rollback()
        raise
