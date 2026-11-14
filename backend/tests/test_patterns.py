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


# --- Step B: the route graph uses the patterns ----------------------------------------------

from app.schemas.journey import JourneyRequest  # noqa: E402
from app.schemas.scenario import Scenario  # noqa: E402
from app.services.journey_service import compare_journey, plan_journey  # noqa: E402
from app.services.route_graph import build_route_graph, route_rides, travel_time_matrix  # noqa: E402
from app.services.simulation_service import apply_scenario, simulate  # noqa: E402
from app.services.walking import WalkingModel  # noqa: E402


def _network(links: dict[tuple[str, str], float], patterns: list[tuple[str, ...]] | None, loop: bool = False) -> nx.DiGraph:
    """Route R over the given (from, to): minutes; ``patterns`` None = no patterns."""
    stop_ids = sorted({s for link in links for s in link})
    stops = [Stop(id=s, name=s, lat=0.0, lon=i * 0.01, activity=1) for i, s in enumerate(stop_ids)]
    connections = [Connection(route_id="R", from_stop_id=u, to_stop_id=v, travel_time_min=t) for (u, v), t in links.items()]
    return build_graph(stops, connections, [Route(id="R", name="R", color="#000000", headway_min=10)],
                       [Pattern("R", p, loop) for p in patterns or []])


# A line whose directions use different streets at the terminus T: out via B, back via C.
TERMINUS = {("A", "B"): 2, ("B", "T"): 2, ("T", "C"): 2, ("C", "A"): 2}


def test_no_staying_on_through_a_terminus_the_trips_end_at() -> None:
    with_patterns = _network(TERMINUS, [("A", "B", "T"), ("T", "C", "A")])
    without = _network(TERMINUS, None)
    # B -> C: off at T and board the return trip (a change: penalty 5), not 4 min straight through.
    assert plan_journey(without, "B", "C", transfer_penalty_min=5).travel_time_min == 4.0  # type: ignore[union-attr]
    plan = plan_journey(with_patterns, "B", "C", transfer_penalty_min=5)
    assert plan is not None and (plan.travel_time_min, plan.transfers) == (9.0, 1)
    assert [leg.stop_ids for leg in plan.legs] == [["B", "T"], ["T", "C"]]


def test_a_loop_the_vehicle_drives_cannot_be_skipped() -> None:
    # The trip passes S twice (S -> K -> S); staying on from A to B must ride the loop.
    links = {("A", "S"): 1, ("S", "K"): 3, ("K", "S"): 3, ("S", "B"): 1}
    pattern = _network(links, [("A", "S", "K", "S", "B")])
    assert plan_journey(_network(links, None), "A", "B", 10).travel_time_min == 2.0  # type: ignore[union-attr]
    stay = plan_journey(pattern, "A", "B", 10)
    assert stay is not None and (stay.travel_time_min, stay.transfers) == (8.0, 0)
    # Getting off at S and boarding a vehicle already past the loop is a change of bus.
    change = plan_journey(pattern, "A", "B", 5)
    assert change is not None and (change.travel_time_min, change.transfers) == (7.0, 1)


def test_a_ring_loop_continues_past_its_first_stop() -> None:
    ring = _network({("A", "B"): 1, ("B", "C"): 1, ("C", "A"): 1}, [("A", "B", "C")], loop=True)
    plan = plan_journey(ring, "C", "B", transfer_penalty_min=5)
    assert plan is not None and (plan.travel_time_min, plan.transfers) == (2.0, 0)  # C -> A -> B, staying on


def test_routes_without_patterns_keep_the_shared_platforms() -> None:
    graph = build_route_graph(_network(TERMINUS, None), 0.0)
    assert all(len(node) == 2 for node in graph.nodes if isinstance(node, tuple))


def test_the_sample_round_trip_no_longer_joins_two_walks(db: Session) -> None:
    # Step A's known limit: SCH and STH closed, the fastest way rode R1 HOS -> CEN -> HOS
    # (out and back, 33.4 min). Now a turn-round is a change: 35.3 min, as before step A.
    sample = build_graph_from_db(db)
    changes = [{"type": "close_stop", "stop_id": "STH"}, {"type": "close_stop", "stop_id": "SCH"}]
    result = simulate(sample, Scenario.model_validate({"changes": changes}), 2.0, True,
                      WalkingModel(5, 1000, between_open_stops=False))
    times = {(j.origin_id, j.destination_id): j.time_after_min for j in result.changed_journeys}
    assert times[("SCH", "STH")] == 35.3


def test_an_added_link_joins_the_route_at_both_ends() -> None:
    line = _network({("A", "B"): 2, ("B", "A"): 2, ("B", "C"): 2, ("C", "B"): 2}, [("A", "B", "C"), ("C", "B", "A")])
    line.add_node("X", name="X", lat=0.0, lon=0.05, activity=1)  # a stop no route serves yet
    extend = {"type": "add_connection", "route_id": "R", "from_stop_id": "C", "to_stop_id": "X",
              "travel_time_min": 3, "both_directions": True}
    request = JourneyRequest(origin_id="A", destination_id="X", changes=[extend])
    after = compare_journey(line, request, transfer_penalty_min=5).after
    assert after is not None and after.transfers == 0  # stays on from A through C onto the new link
    assert [leg.stop_ids for leg in after.legs] == [["A", "B", "C", "X"]]
    back = compare_journey(line, JourneyRequest(origin_id="X", destination_id="A", changes=[extend]), 5).after
    assert back is not None and (back.travel_time_min, back.transfers) == (7.0, 0)


def test_an_added_stop_goes_into_every_pattern_that_drives_the_link(db: Session) -> None:
    # R3 is a ring (two loops); OLD -> UNI is the closing stretch of one of them.
    sample = build_graph_from_db(db)
    change = {"type": "add_stop", "stop_id": "N1", "name": "Ring Corner", "lat": 50.07, "lon": 19.93,
              "route_id": "R3", "from_stop_id": "OLD", "to_stop_id": "UNI", "time_from_min": 1, "time_to_min": 2}
    graph, _ = apply_scenario(sample, Scenario.model_validate({"changes": [change]}))
    assert not route_rides(graph, "R3", "OLD", "UNI") and not route_rides(graph, "R3", "UNI", "OLD")
    assert [graph.edges[a, b]["weight"] for a, b in route_rides(graph, "R3", "OLD", "N1")] == [1]
    assert [graph.edges[a, b]["weight"] for a, b in route_rides(graph, "R3", "N1", "UNI")] == [2]
    assert [graph.edges[a, b]["weight"] for a, b in route_rides(graph, "R3", "UNI", "N1")] == [2]
    assert [graph.edges[a, b]["weight"] for a, b in route_rides(graph, "R3", "N1", "OLD")] == [1]
    # The ring still runs all the way round without a change.
    matrix = travel_time_matrix(graph, ["LIB", "N1", "MUS"])
    assert matrix.get("LIB", "MUS") is not None
