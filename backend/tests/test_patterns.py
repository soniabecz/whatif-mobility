"""Route patterns (Day 14 part 4, step A): how a route's vehicles actually run,
stored with the network (sample seed and GTFS import) and loaded into the graph."""

from pathlib import Path

import networkx as nx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Connection, PatternStop, Route, RoutePattern, Stop
from app.seed.seed_db import sample_lacks_patterns, seed_database
from app.services.network_service import Pattern, build_graph, build_graph_from_db, list_patterns
from tests.test_gtfs_import import _trams


def _count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_sample_routes_run_both_ways_and_the_ring_loops(db: Session) -> None:
    patterns = {(p.route_id, p.stop_ids[:3], p.is_loop) for p in list_patterns(db)}
    assert ("R1", ("NTH", "UNI", "MKT"), False) in patterns
    assert ("R1", ("STH", "HOS", "CEN"), False) in patterns
    assert ("R3", ("UNI", "MUS", "RIV"), True) in patterns
    assert ("R3", ("UNI", "OLD", "LIB"), True) in patterns  # the other way round
    assert len(patterns) == 8  # two per route


def test_reseeding_replaces_the_patterns(db: Session) -> None:
    seed_database(db)
    assert (_count(db, RoutePattern), _count(db, PatternStop)) == (8, 2 * (6 + 5 + 8 + 5))


def test_the_graph_knows_the_patterns(db: Session) -> None:
    graph = build_graph_from_db(db)
    r1 = graph.graph["patterns"]["R1"]
    assert r1[0] == Pattern("R1", ("NTH", "UNI", "MKT", "CEN", "HOS", "STH"))
    assert len(graph.graph["patterns"]) == 4


def _line() -> nx.DiGraph:
    stops = [Stop(id=s, name=s, lat=0.0, lon=float(i), activity=1) for i, s in enumerate("ABCD")]
    links = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")]
    connections = [Connection(route_id="R", from_stop_id=u, to_stop_id=v, travel_time_min=1) for u, v in links]
    return build_graph(stops, connections, [Route(id="R", name="R", color="#000000", headway_min=10)])


def test_a_pattern_splits_where_a_stretch_is_missing() -> None:
    graph = _line()
    graph.remove_edge("B", "C")
    rebuilt = build_graph(
        [Stop(id=s, name=s, lat=0.0, lon=0.0, activity=1) for s in "ABCD"],
        [Connection(route_id="R", from_stop_id=u, to_stop_id=v, travel_time_min=1) for u, v in graph.edges],
        patterns=[Pattern("R", ("A", "B", "C", "D")), Pattern("R", ("A", "B", "C", "D"), is_loop=True)],
    )
    assert rebuilt.graph["patterns"]["R"] == (
        Pattern("R", ("A", "B")), Pattern("R", ("C", "D")),  # the path, split at B -> C
        Pattern("R", ("C", "D", "A", "B")),  # the loop, opened at B -> C
    )


def test_import_stores_the_main_sequence_per_direction(tmp_path: Path, db: Session) -> None:
    from app.services.gtfs_import import write_network

    network = _trams(tmp_path)
    assert [(p.route_id, p.stop_ids) for p in network.patterns] == [
        ("T1", ("S11", "S20", "S30")), ("T1", ("S30", "S20", "S11")), ("T2", ("S30", "S40")),
    ]
    write_network(db, network)
    assert [(p.route_id, p.stop_ids, p.is_loop) for p in list_patterns(db)] == [
        ("T1", ("S11", "S20", "S30"), False), ("T1", ("S30", "S20", "S11"), False), ("T2", ("S30", "S40"), False),
    ]


def test_an_old_sample_without_patterns_is_recognised(db: Session) -> None:
    assert not sample_lacks_patterns(db)
    db.execute(PatternStop.__table__.delete())
    db.execute(RoutePattern.__table__.delete())
    db.commit()
    assert sample_lacks_patterns(db)


def test_an_imported_network_is_never_taken_for_an_old_sample(tmp_path: Path, db: Session) -> None:
    from app.services.gtfs_import import write_network

    write_network(db, _trams(tmp_path))
    db.execute(PatternStop.__table__.delete())
    db.execute(RoutePattern.__table__.delete())
    db.commit()
    assert not sample_lacks_patterns(db)  # it has a data source: re-import it instead
