"""Scenario type "change frequency" (Day 10, part 1b).

A route gets a new headway (minutes between buses). It only changes the
expected wait at that route's boardings, so it has an effect only when
waiting is modelled.
"""

import copy
import json
from itertools import pairwise
from typing import Any

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.main import app
from app.models import Connection, Route, Stop
from app.schemas.journey import JourneyRequest
from app.schemas.scenario import ChangeFrequency, Scenario
from app.services.ai_service import build_system_prompt, interpret
from app.services.journey_service import compare_journey
from app.services.network_service import build_graph, build_graph_from_db
from app.services.simulation_service import ScenarioError, apply_scenario, simulate


def _network(
    routes: dict[str, list[tuple[str, float]]], headways: dict[str, float]
) -> nx.DiGraph:
    stop_ids = sorted({stop for path in routes.values() for stop, _ in path})
    connections = []
    for route_id, path in routes.items():
        for (a, minutes), (b, _) in pairwise(path):
            connections += [
                Connection(route_id=route_id, from_stop_id=a, to_stop_id=b, travel_time_min=minutes),
                Connection(route_id=route_id, from_stop_id=b, to_stop_id=a, travel_time_min=minutes),
            ]
    return build_graph(
        [Stop(id=s, name=s, lat=0.0, lon=0.0) for s in stop_ids],
        connections,
        [Route(id=r, name=f"Route {r}", color="#000000", headway_min=h) for r, h in headways.items()],
    )


# A -R1 3- B -R2 4- C, plus a direct but rare R3 A-C (10 min, every 60 min).
NET = _network(
    {"R1": [("A", 3), ("B", 0)], "R2": [("B", 4), ("C", 0)], "R3": [("A", 10), ("C", 0)]},
    {"R1": 10, "R2": 20, "R3": 60},
)


def _scenario(*changes: dict[str, Any]) -> Scenario:
    return Scenario.model_validate({"changes": list(changes)})


def _freq(route_id: str, headway: float) -> dict[str, Any]:
    return {"type": "change_frequency", "route_id": route_id, "headway_min": headway}


def _times(result: Any) -> dict[tuple[str, str], tuple[float, float | None]]:
    return {(j.origin_id, j.destination_id): (j.time_before_min, j.time_after_min)
            for j in result.changed_journeys}


# --- Schema --------------------------------------------------------------------------------

def test_schema_accepts_a_headway_between_1_and_120() -> None:
    assert isinstance(_scenario(_freq("R1", 1)).changes[0], ChangeFrequency)
    _scenario(_freq("R1", 120))
    for invalid in (0.5, 121, float("inf")):
        with pytest.raises(ValidationError):
            _scenario(_freq("R1", invalid))


def test_schema_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        _scenario({**_freq("R1", 5), "minutes": 5})


# --- Engine --------------------------------------------------------------------------------

def test_more_frequent_route_means_shorter_waits() -> None:
    # R1 every 4 min: wait 2 instead of 5.
    result = simulate(NET, _scenario(_freq("R1", 4)), 2.0, include_waiting=True)
    assert _times(result)[("A", "B")] == (8.0, 5.0)
    assert result.summary.faster > 0 and result.summary.slower == 0


def test_less_frequent_route_means_longer_waits() -> None:
    result = simulate(NET, _scenario(_freq("R2", 40)), 2.0, include_waiting=True)
    assert _times(result)[("B", "C")] == (14.0, 24.0)  # wait 10 -> 20, ride 4


def test_a_frequency_change_can_change_the_route_taken() -> None:
    request = JourneyRequest(origin_id="A", destination_id="C", changes=[_freq("R3", 4)])
    comparison = compare_journey(NET, request, 2.0, include_waiting=True)
    assert comparison.before and comparison.after
    assert [leg.route_id for leg in comparison.before.legs] == ["R1", "R2"]  # 5+3+2+10+4 = 24
    assert [leg.route_id for leg in comparison.after.legs] == ["R3"]  # 2+10 = 12
    assert comparison.after.legs[0].wait_min == 2
    assert (comparison.status, comparison.change_min) == ("faster", -12.0)


def test_later_changes_to_the_same_route_win() -> None:
    result = simulate(NET, _scenario(_freq("R1", 4), _freq("R1", 30)), 2.0, include_waiting=True)
    assert _times(result)[("A", "B")] == (8.0, 18.0)  # wait 15, ride 3


def test_without_waiting_a_frequency_change_has_no_effect() -> None:
    result = simulate(NET, _scenario(_freq("R1", 1)), 2.0, include_waiting=False)
    assert result.changed_journeys == []
    assert result.summary.unchanged == result.summary.total_journeys


def test_unknown_route_is_rejected() -> None:
    with pytest.raises(ScenarioError, match=r"Change 1 \(change_frequency\): unknown route 'R9'"):
        apply_scenario(NET, _scenario(_freq("R9", 5)), 2.0, include_waiting=True)


def test_baseline_is_never_modified() -> None:
    baseline = copy.deepcopy(NET)
    simulate(NET, _scenario(_freq("R1", 4)), 2.0, include_waiting=True)
    assert NET.graph == baseline.graph  # headways included
    assert nx.utils.graphs_equal(NET, baseline)


# --- Sample network, API -------------------------------------------------------------------

@pytest.fixture
def sample(db: Session) -> nx.DiGraph:
    return build_graph_from_db(db)


def test_doubling_the_ring_frequency_on_the_sample(sample: nx.DiGraph) -> None:
    result = simulate(sample, _scenario(_freq("R3", 7.5)), 2.0, include_waiting=True)
    assert result.summary.faster > 0
    assert result.summary.slower == result.summary.impossible == 0


def _use_waiting() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,  # type: ignore[call-arg]
        groq_api_key=None,
        transfer_penalty_min=2.0,
        include_waiting=True,
    )


def test_api_simulates_a_frequency_change(client: TestClient) -> None:
    _use_waiting()
    response = client.post("/api/simulations", json={"changes": [_freq("R4", 5)]})
    assert response.status_code == 200
    assert response.json()["summary"]["faster"] > 0


def test_api_rejects_an_unknown_route(client: TestClient) -> None:
    _use_waiting()
    response = client.post("/api/simulations", json={"changes": [_freq("R9", 5)]})
    assert response.status_code == 422
    assert "unknown route 'R9'" in response.json()["detail"]


# --- AI ------------------------------------------------------------------------------------

class _FakeModel:
    def __init__(self, answer: dict[str, Any]) -> None:
        self.answer = json.dumps(answer)

    def complete_json(self, system_prompt: str, user_text: str, schema: dict) -> str:
        return self.answer


def _ai(*changes: dict[str, Any]) -> dict[str, Any]:
    return {"status": "ok", "changes": list(changes), "message": "Understood."}


def test_prompt_lists_routes_with_their_headways(sample: nx.DiGraph) -> None:
    prompt = build_system_prompt(sample)
    assert "- R3: Ring, a bus every 15 min" in prompt
    assert "change_frequency" in prompt and "twice as often" in prompt


def test_ai_frequency_change_is_accepted(sample: nx.DiGraph) -> None:
    result = interpret("ring twice as often", sample, _FakeModel(_ai(_freq("R3", 7.5))))
    assert result.status == "ok"
    assert result.changes == [ChangeFrequency(type="change_frequency", route_id="R3", headway_min=7.5)]


@pytest.mark.parametrize(
    ("change", "message"),
    [(_freq("R9", 5), "unknown route 'R9'"), (_freq("R1", 500), "not valid")],
)
def test_ai_invalid_frequency_becomes_unclear(
    sample: nx.DiGraph, change: dict[str, Any], message: str
) -> None:
    result = interpret("change a route", sample, _FakeModel(_ai(change)))
    assert (result.status, result.changes) == ("unclear", [])
    assert message in result.message
