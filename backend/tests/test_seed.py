"""Sample network data and the seed function."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Connection, Route, Stop
from app.seed.sample_network import ROUTES, STOPS, SampleRoute, route_segments
from app.seed.seed_db import seed_database


def _count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_sample_network_size_matches_plan() -> None:
    assert 15 <= len(STOPS) <= 20
    assert 3 <= len(ROUTES) <= 4
    assert len({s.id for s in STOPS}) == len(STOPS)


def test_routes_only_use_known_stops() -> None:
    stop_ids = {s.id for s in STOPS}
    for route in ROUTES:
        assert set(route.stop_ids) <= stop_ids, route.id


def test_route_segments_are_two_way_and_loops_close() -> None:
    loop = SampleRoute("L", "Loop", "#000000", ["A", "B", "C"], [1, 2, 3], is_loop=True)

    assert route_segments(loop) == [
        ("A", "B", 1.0), ("B", "A", 1.0),
        ("B", "C", 2.0), ("C", "B", 2.0),
        ("C", "A", 3.0), ("A", "C", 3.0),
    ]


def test_route_with_wrong_number_of_times_is_rejected() -> None:
    bad = SampleRoute("B", "Bad", "#000000", ["A", "B", "C"], [1])
    with pytest.raises(ValueError, match="expected 2 travel times"):
        route_segments(bad)


def test_seed_writes_whole_network(db: Session) -> None:
    assert _count(db, Stop) == len(STOPS)
    assert _count(db, Route) == len(ROUTES)
    assert _count(db, Connection) == sum(len(r.travel_times_min) * 2 for r in ROUTES)


def test_seed_is_idempotent(db: Session) -> None:
    seed_database(db)

    assert _count(db, Stop) == len(STOPS)
    assert _count(db, Connection) == sum(len(r.travel_times_min) * 2 for r in ROUTES)


def test_database_rejects_non_positive_travel_time(db: Session) -> None:
    db.add(Connection(route_id="R1", from_stop_id="CEN", to_stop_id="AIR", travel_time_min=0))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_database_rejects_connection_to_missing_stop(db: Session) -> None:
    db.add(Connection(route_id="R1", from_stop_id="CEN", to_stop_id="XXX", travel_time_min=3))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
