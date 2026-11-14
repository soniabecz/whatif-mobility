"""Load the sample network into the database."""

from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.database import Base

from app.models import Connection, NetworkSource, Route, RoutePattern, Stop
from app.seed.sample_network import ROUTES, STOPS, route_patterns, route_segments, stop_coordinates
from app.services.network_service import add_patterns, delete_network


def outdated_tables(engine: Engine) -> list[str]:
    """Existing tables whose columns differ from the models (missing tables are
    fine: ``create_all`` adds them). There are no migrations; see
    app/seed/__main__.py for what is rebuilt."""
    inspector = inspect(engine)
    outdated = []
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        if existing != {column.name for column in table.columns}:
            outdated.append(table.name)
    return outdated


def schema_is_current(engine: Engine) -> bool:
    return not outdated_tables(engine)


def prepare_tables(engine: Engine) -> None:
    """Create missing tables; rebuild outdated NETWORK tables (generated data).

    Saved scenarios are user data: if their table is outdated, stop (SystemExit)
    instead of dropping it.
    """
    from app.models import NETWORK_TABLES

    outdated = outdated_tables(engine)
    user_tables = [name for name in outdated if name not in NETWORK_TABLES]
    if user_tables:
        raise SystemExit(
            f"Tables with saved user data are outdated ({', '.join(user_tables)}). "
            "They are not dropped automatically: back up the database file, then update "
            "or delete those tables by hand."
        )
    if outdated:
        print(f"Network tables are outdated ({', '.join(outdated)}): rebuilding them from the models.")
        Base.metadata.drop_all(engine, tables=[Base.metadata.tables[name] for name in NETWORK_TABLES])
    Base.metadata.create_all(engine)


def network_is_empty(db: Session) -> bool:
    """True when no stops are stored yet (fresh or never-seeded database)."""
    return db.scalar(select(Stop.id).limit(1)) is None


def sample_lacks_patterns(db: Session) -> bool:
    """True for a sample network seeded before routes had patterns (Day 14
    part 4): it has stops but neither patterns nor a data source. Imported
    networks are never reseeded; re-import them instead."""
    return (
        not network_is_empty(db)
        and db.scalar(select(RoutePattern.id).limit(1)) is None
        and db.scalar(select(NetworkSource.id).limit(1)) is None
    )


def seed_database(db: Session) -> None:
    """Replace all network data with the sample network (idempotent).

    Runs in one transaction: either the whole network is written or nothing.
    """
    try:
        delete_network(db)  # the sample is invented: no data source either

        for s in STOPS:
            lat, lon = stop_coordinates(s)
            db.add(Stop(id=s.id, name=s.name, lat=lat, lon=lon, activity=s.activity))
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
            add_patterns(db, r.id, route_patterns(r))
        db.commit()
    except Exception:
        db.rollback()
        raise
