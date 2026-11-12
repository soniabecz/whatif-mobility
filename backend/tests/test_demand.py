"""Demand weighting (Day 10, part 2).

A journey weighs origin activity x destination activity (INVENTED stop levels
1-3). Only shares (%) and averages are reported, never passenger numbers.
With equal levels the weighted figures equal the unweighted ones.
"""

import copy
from itertools import pairwise
from typing import Any

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Connection, Stop
from app.schemas.scenario import Scenario
from app.seed.sample_network import STOPS
from app.services.network_service import build_graph, build_graph_from_db
from app.services.simulation_service import simulate


def _line(activity: dict[str, int], times: list[float]) -> nx.DiGraph:
    """One two-way route through the stops in order (activity keys)."""
    stop_ids = list(activity)
    connections = []
    for (a, b), minutes in zip(pairwise(stop_ids), times, strict=True):
        connections += [
            Connection(route_id="R1", from_stop_id=a, to_stop_id=b, travel_time_min=minutes),
            Connection(route_id="R1", from_stop_id=b, to_stop_id=a, travel_time_min=minutes),
        ]
    stops = [Stop(id=s, name=s, lat=0.0, lon=0.0, activity=level) for s, level in activity.items()]
    return build_graph(stops, connections)


def _scenario(*changes: dict[str, Any]) -> Scenario:
    return Scenario.model_validate({"changes": list(changes)})


# A (major) -3 min- B (quiet) -4 min- C (quiet).
# Journey weights: A<->B 3, A<->C 3, B<->C 1; total 3+3+3+3+1+1 = 14.
LINE = _line({"A": 3, "B": 1, "C": 1}, [3, 4])
SLOW_BC = {"type": "change_travel_time", "from_stop_id": "B", "to_stop_id": "C", "travel_time_min": 6}


def test_shares_are_weighted_by_origin_times_destination() -> None:
    result = simulate(LINE, _scenario({"type": "remove_connection", "from_stop_id": "B", "to_stop_id": "C"}))
    weighted = result.summary.demand_weighted
    # Impossible: A<->C (3 + 3) and B<->C (1 + 1) = 8 of 14.
    assert weighted.impossible_pct == 57.1
    assert weighted.unchanged_pct == 42.9
    assert result.summary.impossible == 4  # unweighted: 4 of 6 journeys


def test_trips_to_or_from_a_closed_stop() -> None:
    weighted = simulate(LINE, _scenario({"type": "close_stop", "stop_id": "A"})).summary.demand_weighted
    assert weighted.to_or_from_closed_stop_pct == 85.7  # A's four journeys: 12 of 14


def test_weighted_average_time() -> None:
    summary = simulate(LINE, _scenario(SLOW_BC)).summary
    # Before: AB 3, AC 7, BC 4 (each both ways). Weighted (3*3+3*7+1*4)*2/14 = 68/14.
    assert summary.demand_weighted.average_time_before_min == 4.9
    assert summary.average_time_before_min == 4.7  # unweighted: 28/6
    # After (B-C 6 min): AB 3, AC 9, BC 6 -> (9+27+6)*2/14 = 84/14 = 6.0
    assert summary.demand_weighted.average_time_after_min == 6.0
    assert summary.demand_weighted.slower_pct == 57.1  # A<->C and B<->C: 8 of 14


@pytest.fixture
def sample(db: Session) -> nx.DiGraph:
    return build_graph_from_db(db)


SCENARIOS = [
    [{"type": "close_stop", "stop_id": "CEN"}],
    [{"type": "remove_connection", "from_stop_id": "TEC", "to_stop_id": "AIR"}],
    [{"type": "change_travel_time", "from_stop_id": "MKT", "to_stop_id": "CEN", "travel_time_min": 1}],
    [{"type": "change_frequency", "route_id": "R3", "headway_min": 5}],
]


@pytest.mark.parametrize("changes", SCENARIOS)
@pytest.mark.parametrize(("penalty", "waiting"), [(0.0, False), (2.0, True)])
def test_equal_levels_reproduce_the_unweighted_figures(
    sample: nx.DiGraph, changes: list[dict[str, Any]], penalty: float, waiting: bool
) -> None:
    equal = copy.deepcopy(sample)
    for stop_id in equal.nodes:
        equal.nodes[stop_id]["activity"] = 2

    summary = simulate(equal, _scenario(*changes), penalty, waiting).summary
    weighted = summary.demand_weighted

    def pct(count: int) -> float:
        return round(100 * count / summary.total_journeys, 1)

    assert weighted.unchanged_pct == pct(summary.unchanged)
    assert weighted.slower_pct == pct(summary.slower)
    assert weighted.faster_pct == pct(summary.faster)
    assert weighted.impossible_pct == pct(summary.impossible)
    assert weighted.to_or_from_closed_stop_pct == pct(summary.to_or_from_closed_stop)
    assert weighted.average_time_before_min == summary.average_time_before_min
    assert weighted.average_time_after_min == summary.average_time_after_min


@pytest.mark.parametrize("changes", SCENARIOS)
def test_shares_add_up_to_100(sample: nx.DiGraph, changes: list[dict[str, Any]]) -> None:
    weighted = simulate(sample, _scenario(*changes), 2.0, True).summary.demand_weighted
    total = (
        weighted.unchanged_pct + weighted.slower_pct + weighted.faster_pct
        + weighted.impossible_pct + weighted.newly_possible_pct
        + weighted.to_or_from_closed_stop_pct
    )
    assert total == pytest.approx(100, abs=0.3)  # each share is rounded to 0.1


def test_sample_levels_are_the_agreed_ones(sample: nx.DiGraph) -> None:
    levels = {stop_id: sample.nodes[stop_id]["activity"] for stop_id in sample.nodes}
    assert {s for s, level in levels.items() if level == 3} == {"CEN", "MKT", "UNI"}
    assert {s for s, level in levels.items() if level == 1} == {"NTH", "WST", "LIB", "RIV", "EST", "MUS"}
    assert len(levels) == len(STOPS)


def test_closing_a_major_stop_weighs_more_than_its_journey_count(sample: nx.DiGraph) -> None:
    summary = simulate(sample, _scenario({"type": "close_stop", "stop_id": "CEN"}), 2.0, True).summary
    unweighted = 100 * summary.to_or_from_closed_stop / summary.total_journeys  # 12.5%
    assert summary.demand_weighted.to_or_from_closed_stop_pct > unweighted


def test_baseline_is_never_modified(sample: nx.DiGraph) -> None:
    snapshot = copy.deepcopy(sample)
    simulate(sample, _scenario(*SCENARIOS[0]), 2.0, True)
    assert nx.utils.graphs_equal(sample, snapshot)
    assert dict(sample.nodes(data=True)) == dict(snapshot.nodes(data=True))


def test_api_returns_the_weighted_figures(client: TestClient) -> None:
    response = client.post("/api/simulations", json={"changes": SCENARIOS[0]})
    assert response.status_code == 200
    weighted = response.json()["summary"]["demand_weighted"]
    assert set(weighted) == {
        "unchanged_pct", "slower_pct", "faster_pct", "impossible_pct", "newly_possible_pct",
        "to_or_from_closed_stop_pct", "average_time_before_min", "average_time_after_min",
    }
