"""Load the sample network into the database."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Connection, Route, Stop
from app.seed.sample_network import ROUTES, STOPS, route_segments, stop_coordinates


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
            db.add(Route(id=r.id, name=r.name, color=r.color))
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
