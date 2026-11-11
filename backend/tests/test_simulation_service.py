"""Simulation engine: applying changes and computing metrics.

Small hand-made networks are used where exact expected numbers matter;
the sample network is used for realistic end-to-end checks.
"""

import copy
import re
from itertools import pairwise
from typing import Any

import networkx as nx
import pytest
from sqlalchemy.orm import Session

from app.models import Connection, Stop
from app.schemas.scenario import Scenario
from app.services.network_service import build_graph, build_graph_from_db
from app.services.simulation_service import ScenarioError, apply_scenario, simulate


def _network(routes: dict[str, list[tuple[str, float]]]) -> nx.DiGraph:
    """Build a two-way network from {route: [(stop, minutes_to_next), ...]}."""
    stop_ids = sorted({stop for path in routes.values() for stop, _ in path})
    connections: list[Connection] = []
    for route_id, path in routes.items():
        for (a, minutes), (b, _) in pairwise(path):
            connections.append(Connection(route_id=route_id, from_stop_id=a,
                                          to_stop_id=b, travel_time_min=minutes))
            connections.append(Connection(route_id=route_id, from_stop_id=b,
                                          to_stop_id=a, travel_time_min=minutes))
    stops = [Stop(id=s, name=s, lat=0.0, lon=0.0) for s in stop_ids]
    return build_graph(stops, connections)


def _scenario(*changes: dict[str, Any]) -> Scenario:
    return Scenario.model_validate({"changes": list(changes)})


@pytest.fixture
def line() -> nx.DiGraph:
    """A --2-- B --3-- C on route R1, both directions."""
    return _network({"R1": [("A", 2), ("B", 3), ("C", 0)]})


@pytest.fixture
def cross() -> nx.DiGraph:
    """R1: A-X-B and R2: C-X-D, crossing at X (the only transfer point)."""
    return _network({
        "R1": [("A", 1), ("X", 1), ("B", 0)],
        "R2": [("C", 1), ("X", 1), ("D", 0)],
    })


@pytest.fixture
def sample(db: Session) -> nx.DiGraph:
    return build_graph_from_db(db)


# --- Baseline is never modified -----------------------------------------------

@pytest.mark.parametrize(
    "change",
    [
        {"type": "close_stop", "stop_id": "CEN"},
        {"type": "remove_connection", "from_stop_id": "MKT", "to_stop_id": "CEN"},
        {"type": "change_travel_time", "from_stop_id": "MKT", "to_stop_id": "CEN",
         "travel_time_min": 30},
    ],
)
def test_baseline_graph_is_never_modified(sample: nx.DiGraph, change: dict[str, Any]) -> None:
    snapshot = copy.deepcopy(sample)

    simulate(sample, _scenario(change))

    assert list(sample.nodes(data=True)) == list(snapshot.nodes(data=True))
    assert list(sample.edges(data=True)) == list(snapshot.edges(data=True))


def test_failed_scenario_leaves_baseline_unmodified(sample: nx.DiGraph) -> None:
    snapshot = copy.deepcopy(sample)

    with pytest.raises(ScenarioError):
        simulate(sample, _scenario(
            {"type": "close_stop", "stop_id": "CEN"},
            {"type": "close_stop", "stop_id": "NOPE"},
        ))

    assert list(sample.edges(data=True)) == list(snapshot.edges(data=True))


# --- close_stop (buses drive through) ---------------------------------------

def test_closed_stop_is_bypassed_on_the_same_route(line: nx.DiGraph) -> None:
    graph, closed = apply_scenario(line, _scenario({"type": "close_stop", "stop_id": "B"}))

    assert closed == {"B"}
    assert "B" not in graph
    assert graph.edges["A", "C"]["route_times"] == {"R1": 5}
    assert graph.edges["C", "A"]["weight"] == 5


def test_journeys_through_closed_stop_keep_their_time(line: nx.DiGraph) -> None:
    summary = simulate(line, _scenario({"type": "close_stop", "stop_id": "B"})).summary

    assert summary.total_journeys == 6
    assert summary.to_or_from_closed_stop == 4  # A-B, B-A, B-C, C-B
    assert summary.unchanged == 2  # A-C and C-A still take 5 min
    assert summary.slower == summary.faster == summary.impossible == 0


def test_closing_a_transfer_stop_makes_transfers_impossible(cross: nx.DiGraph) -> None:
    result = simulate(cross, _scenario({"type": "close_stop", "stop_id": "X"}))

    s = result.summary
    assert (s.total_journeys, s.to_or_from_closed_stop) == (20, 8)
    assert s.unchanged == 4  # A<->B (R1), C<->D (R2) drive through X
    assert s.impossible == 8  # every journey that had to change bus at X
    assert {(j.origin_id, j.destination_id) for j in result.changed_journeys} == {
        (o, d) for o in "AB" for d in "CD"} | {(o, d) for o in "CD" for d in "AB"}


def test_bypass_uses_each_routes_own_travel_time(sample: nx.DiGraph) -> None:
    graph, _ = apply_scenario(sample, _scenario({"type": "close_stop", "stop_id": "CEN"}))

    # MKT->CEN is 3 min on R1 but 2 min on R4; the bypasses must not mix them.
    assert graph.edges["MKT", "HOS"]["route_times"] == {"R1": 7.0}  # 3 + 4
    assert graph.edges["MKT", "STD"]["route_times"] == {"R4": 6.0}  # 2 + 4
    assert graph.edges["LIB", "RIV"]["route_times"] == {"R2": 8.0}  # 4 + 4
    # No route runs MKT -> CEN -> RIV, so there is no such bypass.
    assert not graph.has_edge("MKT", "RIV")


def test_closing_two_adjacent_stops_chains_bypasses() -> None:
    graph = _network({"R1": [("A", 1), ("B", 2), ("C", 3), ("D", 0)]})

    modified, _ = apply_scenario(graph, _scenario(
        {"type": "close_stop", "stop_id": "B"},
        {"type": "close_stop", "stop_id": "C"},
    ))

    assert modified.edges["A", "D"]["route_times"] == {"R1": 6}


# --- remove_connection ---------------------------------------------------------

def test_remove_connection_both_directions(line: nx.DiGraph) -> None:
    result = simulate(line, _scenario(
        {"type": "remove_connection", "from_stop_id": "B", "to_stop_id": "C"}))

    assert result.summary.impossible == 4  # A->C, B->C, C->A, C->B
    assert result.summary.unchanged == 2


def test_remove_connection_one_direction(line: nx.DiGraph) -> None:
    result = simulate(line, _scenario(
        {"type": "remove_connection", "from_stop_id": "B", "to_stop_id": "C",
         "both_directions": False}))

    assert [(j.origin_id, j.destination_id, j.status) for j in result.changed_journeys] == [
        ("A", "C", "impossible"),
        ("B", "C", "impossible"),
    ]
    impacts = {i.stop_id: i for i in result.stop_impacts}
    assert (impacts["C"].affected_journeys, impacts["C"].impossible_journeys) == (2, 2)
    assert impacts["C"].average_change_min is None
    assert result.most_affected_stop_ids == ["C", "A", "B"]


def test_removing_a_shared_link_affects_every_route_on_it(sample: nx.DiGraph) -> None:
    graph, _ = apply_scenario(sample, _scenario(
        {"type": "remove_connection", "from_stop_id": "MKT", "to_stop_id": "CEN"}))

    assert not graph.has_edge("MKT", "CEN")  # gone for R1 and R4
    assert not graph.has_edge("CEN", "MKT")


# --- change_travel_time --------------------------------------------------------

def test_slower_link_gives_exact_metrics(line: nx.DiGraph) -> None:
    result = simulate(line, _scenario(
        {"type": "change_travel_time", "from_stop_id": "B", "to_stop_id": "C",
         "travel_time_min": 6}))

    s = result.summary
    assert (s.unchanged, s.slower, s.faster, s.impossible) == (2, 4, 0, 0)
    assert s.average_time_before_min == 3.3  # (2+5+2+3+5+3) / 6
    assert s.average_time_after_min == 5.3  # (2+8+2+6+8+6) / 6
    assert s.total_time_change_min == 12.0
    assert s.largest_increase is not None
    assert (s.largest_increase.origin_id, s.largest_increase.destination_id) == ("A", "C")
    assert s.largest_increase.change_min == 3.0
    assert all(j.change_min == 3.0 for j in result.changed_journeys)


def test_faster_link(line: nx.DiGraph) -> None:
    result = simulate(line, _scenario(
        {"type": "change_travel_time", "from_stop_id": "B", "to_stop_id": "C",
         "travel_time_min": 1}))

    assert result.summary.faster == 4
    assert result.summary.total_time_change_min == -8.0
    assert result.summary.largest_increase is None


def test_new_time_applies_to_every_route_on_the_link(sample: nx.DiGraph) -> None:
    graph, _ = apply_scenario(sample, _scenario(
        {"type": "change_travel_time", "from_stop_id": "MKT", "to_stop_id": "CEN",
         "travel_time_min": 10, "both_directions": False}))

    assert graph.edges["MKT", "CEN"]["route_times"] == {"R1": 10, "R4": 10}
    assert graph.edges["MKT", "CEN"]["weight"] == 10
    assert graph.edges["CEN", "MKT"]["weight"] == 2.0  # other direction untouched


# --- Errors --------------------------------------------------------------------

@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ([{"type": "close_stop", "stop_id": "XXX"}],
         "Change 1 (close_stop): unknown stop 'XXX'"),
        ([{"type": "remove_connection", "from_stop_id": "NTH", "to_stop_id": "AIR"}],
         "Change 1 (remove_connection): no connection from 'NTH' to 'AIR'"),
        ([{"type": "close_stop", "stop_id": "CEN"}, {"type": "close_stop", "stop_id": "CEN"}],
         "Change 2 (close_stop): stop 'CEN' is already closed"),
        ([{"type": "close_stop", "stop_id": "CEN"},
          {"type": "change_travel_time", "from_stop_id": "MKT", "to_stop_id": "CEN",
           "travel_time_min": 5}],
         "Change 2 (change_travel_time): stop 'CEN' is already closed"),
        ([{"type": "remove_connection", "from_stop_id": "MKT", "to_stop_id": "CEN"},
          {"type": "remove_connection", "from_stop_id": "MKT", "to_stop_id": "CEN"}],
         "Change 2 (remove_connection): no connection from 'MKT' to 'CEN'"),
    ],
)
def test_invalid_scenarios_raise_clear_errors(
    sample: nx.DiGraph, changes: list[dict[str, Any]], message: str
) -> None:
    with pytest.raises(ScenarioError, match=re.escape(message)):
        simulate(sample, _scenario(*changes))


def test_both_directions_requires_the_reverse_link() -> None:
    one_way = build_graph(
        [Stop(id=s, name=s, lat=0.0, lon=0.0) for s in "AB"],
        [Connection(route_id="R1", from_stop_id="A", to_stop_id="B", travel_time_min=1)],
    )

    with pytest.raises(ScenarioError, match="no connection from 'B' to 'A'"):
        simulate(one_way, _scenario(
            {"type": "remove_connection", "from_stop_id": "A", "to_stop_id": "B"}))


# --- Sample network end-to-end ---------------------------------------------------

def test_counts_add_up_on_sample_network(sample: nx.DiGraph) -> None:
    result = simulate(sample, _scenario({"type": "close_stop", "stop_id": "CEN"}))

    s = result.summary
    assert s.total_journeys == 16 * 15
    assert s.to_or_from_closed_stop == 2 * 15
    assert s.unchanged + s.slower + s.faster + s.impossible + s.to_or_from_closed_stop \
        == s.total_journeys
    assert len(result.changed_journeys) == s.slower + s.faster + s.impossible
    assert [i.stop_id for i in result.stop_impacts] == sorted(sample.nodes)
    assert next(i for i in result.stop_impacts if i.stop_id == "CEN").closed
    assert 0 < len(result.most_affected_stop_ids) <= 5


def test_simulation_is_deterministic(sample: nx.DiGraph) -> None:
    scenario = _scenario(
        {"type": "close_stop", "stop_id": "CEN"},
        {"type": "change_travel_time", "from_stop_id": "RIV", "to_stop_id": "STD",
         "travel_time_min": 7.5},
    )

    assert simulate(sample, scenario).model_dump() == simulate(sample, scenario).model_dump()
