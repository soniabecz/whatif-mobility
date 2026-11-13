"""Comparing two scenarios (Day 13): both simulated against the same baseline;
journey times under A and B must match each scenario's own simulation."""

from typing import Any

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.schemas.scenario import Scenario
from app.services.comparison_service import compare
from app.services.network_service import build_graph_from_db
from app.services.simulation_service import ScenarioError, simulate
from app.services.walking import WalkingModel

CLOSE_CEN = {"type": "close_stop", "stop_id": "CEN"}
SLOW = {"type": "change_travel_time", "from_stop_id": "RIV", "to_stop_id": "EST", "travel_time_min": 9,
        "both_directions": True}
ROUTE = {"type": "add_route", "route_id": "R5", "name": "Cross Town", "color": "#7c3aed", "headway_min": 12,
         "stop_ids": ["OLD", "MKT", "RIV"], "travel_times_min": [3, 4], "is_loop": False, "both_directions": True}
CUT_AIR = {"type": "remove_connection", "from_stop_id": "TEC", "to_stop_id": "AIR", "both_directions": True}


@pytest.fixture
def sample(db: Session) -> nx.DiGraph:
    return build_graph_from_db(db)


def _scenario(*changes: dict[str, Any]) -> Scenario:
    return Scenario.model_validate({"changes": list(changes)})


def _times_after(sample: nx.DiGraph, scenario: Scenario, **settings: Any) -> dict[tuple[str, str], float | None]:
    """Times of the journeys the scenario's own simulation reports as changed."""
    result = simulate(sample, scenario, **settings)
    return {(j.origin_id, j.destination_id): j.time_after_min for j in result.changed_journeys}


SETTINGS = {"transfer_penalty_min": 2.0, "include_waiting": True, "walking": WalkingModel(5, 1000)}


def test_summaries_are_each_scenarios_own(sample: nx.DiGraph) -> None:
    a, b = _scenario(CLOSE_CEN), _scenario(SLOW)
    result = compare(sample, a, b, **SETTINGS)
    assert result.a == simulate(sample, a, **SETTINGS).summary
    assert result.b == simulate(sample, b, **SETTINGS).summary


def test_counts_add_up(sample: nx.DiGraph) -> None:
    result = compare(sample, _scenario(CLOSE_CEN), _scenario(SLOW), **SETTINGS)
    assert result.compared_journeys == 240  # walking: nothing excluded
    assert (result.same + result.a_faster + result.b_faster + result.only_possible_in_a
            + result.only_possible_in_b + result.impossible_in_both) == 240


def test_differences_match_both_simulations(sample: nx.DiGraph) -> None:
    a, b = _scenario(SLOW), _scenario(ROUTE)
    result = compare(sample, a, b, **SETTINGS)
    after_a = _times_after(sample, a, **SETTINGS)
    after_b = _times_after(sample, b, **SETTINGS)
    assert result.largest_differences
    for d in result.largest_differences:
        key = (d.origin_id, d.destination_id)
        time_a = after_a.get(key, d.time_baseline_min)  # unchanged = baseline time
        time_b = after_b.get(key, d.time_baseline_min)
        assert (d.time_a_min, d.time_b_min) == (time_a, time_b)
        assert d.difference_min == round(time_a - time_b, 1)  # type: ignore[operator]
    gaps = [abs(d.difference_min or 0) for d in result.largest_differences]
    assert gaps == sorted(gaps, reverse=True) and len(gaps) <= 10


def test_journeys_possible_in_only_one_come_first(sample: nx.DiGraph) -> None:
    result = compare(sample, _scenario(CUT_AIR), _scenario(SLOW), **SETTINGS)
    assert result.only_possible_in_b == 30 and result.only_possible_in_a == 0  # the airport is cut off in A
    first = result.largest_differences[0]
    assert (first.time_a_min, first.difference_min) == (None, None) and first.time_b_min is not None


def test_identical_scenarios_have_no_differences(sample: nx.DiGraph) -> None:
    result = compare(sample, _scenario(SLOW), _scenario(SLOW), **SETTINGS)
    assert (result.same, result.largest_differences) == (240, [])


def test_closed_stops_without_walking_are_left_out(sample: nx.DiGraph) -> None:
    result = compare(sample, _scenario(CLOSE_CEN), _scenario(SLOW))
    assert result.compared_journeys == 240 - 30


def test_a_scenario_that_does_not_fit_is_an_error(sample: nx.DiGraph) -> None:
    with pytest.raises(ScenarioError, match="unknown stop 'XYZ'"):
        compare(sample, _scenario(SLOW), _scenario({"type": "close_stop", "stop_id": "XYZ"}))


def test_api(client: TestClient) -> None:
    response = client.post("/api/comparisons", json={"a": [CLOSE_CEN], "b": [SLOW]})
    assert response.status_code == 200
    body = response.json()
    simulation = client.post("/api/simulations", json={"changes": [CLOSE_CEN]}).json()
    assert body["a"] == simulation["summary"]
    assert client.post("/api/comparisons", json={"a": [CLOSE_CEN], "b": []}).status_code == 422
    bad = client.post("/api/comparisons", json={"a": [CLOSE_CEN], "b": [{"type": "close_stop", "stop_id": "XYZ"}]})
    assert bad.status_code == 422 and "unknown stop 'XYZ'" in bad.json()["detail"]
