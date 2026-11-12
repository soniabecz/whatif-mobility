"""Scenario type "add connection" (Day 11, part 1).

An existing route also runs directly between two stops (an extension or a
shortcut). At least one stop must already be on the route; a stop the route
did not serve gets a platform (and the route's wait) for it.
"""

import copy
import json
from itertools import pairwise, permutations
from typing import Any

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models import Connection, Route, Stop
from app.schemas.journey import JourneyRequest
from app.schemas.scenario import AddConnection, Scenario
from app.services.ai_service import build_system_prompt, interpret
from app.services.journey_service import compare_journey
from app.services.network_service import build_graph, build_graph_from_db
from app.services.simulation_service import ScenarioError, apply_scenario, simulate


def _network(
    routes: dict[str, list[tuple[str, float]]],
    headways: dict[str, float],
    extra_stops: tuple[str, ...] = (),
) -> nx.DiGraph:
    stop_ids = sorted({stop for path in routes.values() for stop, _ in path} | set(extra_stops))
    connections = []
    for route_id, path in routes.items():
        for (a, minutes), (b, _) in pairwise(path):
            connections += [
                Connection(route_id=route_id, from_stop_id=a, to_stop_id=b, travel_time_min=minutes),
                Connection(route_id=route_id, from_stop_id=b, to_stop_id=a, travel_time_min=minutes),
            ]
    return build_graph(
        [Stop(id=s, name=s, lat=0.0, lon=0.0, activity=1) for s in stop_ids],
        connections,
        [Route(id=r, name=r, color="#000000", headway_min=h) for r, h in headways.items()],
    )


def _add(route: str, a: str, b: str, minutes: float, both: bool = True) -> dict[str, Any]:
    return {"type": "add_connection", "route_id": route, "from_stop_id": a, "to_stop_id": b,
            "travel_time_min": minutes, "both_directions": both}


def _scenario(*changes: dict[str, Any]) -> Scenario:
    return Scenario.model_validate({"changes": list(changes)})


def _times(result: Any) -> dict[tuple[str, str], tuple[float, float | None, str]]:
    return {(j.origin_id, j.destination_id): (j.time_before_min, j.time_after_min, j.status)
            for j in result.changed_journeys}


# A -R1 3- B -R1 4- C, and R2 C -5- D. R1 every 10 min, R2 every 20.
NET = _network(
    {"R1": [("A", 3), ("B", 4), ("C", 0)], "R2": [("C", 5), ("D", 0)]}, {"R1": 10, "R2": 20}
)


# --- Schema --------------------------------------------------------------------------------

def test_schema() -> None:
    assert isinstance(_scenario(_add("R1", "A", "C", 5)).changes[0], AddConnection)
    for invalid in (_add("R1", "A", "A", 5), _add("R1", "A", "C", 0), _add("R1", "A", "C", 601),
                    {**_add("R1", "A", "C", 5), "speed": 1}):
        with pytest.raises(ValidationError):
            _scenario(invalid)


# --- Engine --------------------------------------------------------------------------------

def test_a_shortcut_makes_journeys_faster() -> None:
    # A -> C: 3 + 4 = 7 min on R1; the shortcut takes 5.
    times = _times(simulate(NET, _scenario(_add("R1", "A", "C", 5))))
    assert times[("A", "C")] == (7.0, 5.0, "faster")
    assert times[("C", "A")] == (7.0, 5.0, "faster")


def test_one_way_shortcut() -> None:
    times = _times(simulate(NET, _scenario(_add("R1", "A", "C", 5, both=False))))
    assert ("A", "C") in times and ("C", "A") not in times


def test_an_extension_serves_a_new_stop_with_the_route_s_wait() -> None:
    # R1 extended from C to D (2 min). R1 never stopped at D before.
    graph, _ = apply_scenario(NET, _scenario(_add("R1", "C", "D", 2)), 2.0, include_waiting=True)
    assert graph.edges["D", ("D", "R1")]["wait_min"] == 5  # half of R1's 10 min
    # A -> D: before R1 to C (wait 5 + 7) + change (2 + wait 10) + R2 5 = 29;
    # after: stay on R1 (wait 5 + 7 + 2) = 14.
    times = _times(simulate(NET, _scenario(_add("R1", "C", "D", 2)), 2.0, include_waiting=True))
    assert times[("A", "D")] == (29.0, 14.0, "faster")


def test_later_changes_can_retime_or_remove_the_new_link() -> None:
    retimed = simulate(NET, _scenario(
        _add("R1", "A", "C", 5),
        {"type": "change_travel_time", "from_stop_id": "A", "to_stop_id": "C", "travel_time_min": 6},
    ))
    assert _times(retimed)[("A", "C")] == (7.0, 6.0, "faster")
    removed = simulate(NET, _scenario(
        _add("R1", "A", "C", 5), {"type": "remove_connection", "from_stop_id": "A", "to_stop_id": "C"},
    ))
    assert removed.changed_journeys == []


def test_a_frequency_change_also_applies_to_the_new_stop() -> None:
    graph, _ = apply_scenario(
        NET,
        _scenario(_add("R1", "C", "D", 2), {"type": "change_frequency", "route_id": "R1", "headway_min": 4}),
        2.0,
        include_waiting=True,
    )
    assert graph.edges["D", ("D", "R1")]["wait_min"] == 2


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_add("R9", "A", "C", 5), "unknown route 'R9'"),
        (_add("R2", "A", "B", 5), "route 'R2' stops at neither 'A' nor 'B'"),
        (_add("R1", "A", "B", 5), "route 'R1' already runs from 'A' to 'B'"),
        (_add("R1", "A", "X", 5), "unknown stop 'X'"),
    ],
)
def test_invalid_connections_are_rejected(change: dict[str, Any], message: str) -> None:
    with pytest.raises(ScenarioError, match=r"Change 1 \(add_connection\): " + message):
        apply_scenario(NET, _scenario(change))


def test_connecting_a_closed_stop_is_rejected() -> None:
    with pytest.raises(ScenarioError, match="Change 2 .*'C' is already closed"):
        apply_scenario(NET, _scenario({"type": "close_stop", "stop_id": "C"}, _add("R1", "A", "C", 5)))


def test_a_stop_no_route_served_becomes_newly_possible() -> None:
    lonely = _network({"R1": [("A", 3), ("B", 0)]}, {"R1": 10}, extra_stops=("Z",))
    result = simulate(lonely, _scenario(_add("R1", "B", "Z", 4)))
    summary = result.summary
    # A<->Z and B<->Z: impossible before, possible after; no "before" time to compare.
    assert (summary.newly_possible, summary.unchanged, summary.total_journeys) == (4, 2, 6)
    assert result.changed_journeys == []
    assert summary.demand_weighted.newly_possible_pct == pytest.approx(66.7)

    comparison = compare_journey(lonely, JourneyRequest(origin_id="A", destination_id="Z",
                                                        changes=[_add("R1", "B", "Z", 4)]))
    assert comparison.status == "new" and comparison.before is None
    assert comparison.after is not None and comparison.after.travel_time_min == 7


def test_baseline_is_never_modified() -> None:
    snapshot = copy.deepcopy(NET)
    simulate(NET, _scenario(_add("R1", "C", "D", 2)), 2.0, include_waiting=True)
    assert nx.utils.graphs_equal(NET, snapshot)
    assert NET.graph == snapshot.graph


# --- Sample network, API, AI ---------------------------------------------------------------

@pytest.fixture
def sample(db: Session) -> nx.DiGraph:
    return build_graph_from_db(db)


EXTEND_R2 = _add("R2", "EST", "TEC", 5)  # East Gate to Tech Park; R2 serves EST, not TEC


def test_extending_a_route_on_the_sample(sample: nx.DiGraph) -> None:
    summary = simulate(sample, _scenario(EXTEND_R2), 2.0, True).summary
    assert summary.faster > 0 and summary.slower == summary.impossible == 0


def test_explorer_agrees_with_simulation(sample: nx.DiGraph) -> None:
    simulation = simulate(sample, _scenario(EXTEND_R2), 2.0, True)
    changed = {(j.origin_id, j.destination_id): j for j in simulation.changed_journeys}
    for origin, destination in permutations(sorted(sample.nodes), 2):
        request = JourneyRequest(origin_id=origin, destination_id=destination, changes=[EXTEND_R2])
        result = compare_journey(sample, request, 2.0, True)
        expected = changed.get((origin, destination))
        if expected is None:
            assert result.status == "unchanged", (origin, destination)
        else:
            assert (result.status, result.change_min) == (expected.status, expected.change_min)


def test_api(client: TestClient) -> None:
    assert client.post("/api/simulations", json={"changes": [EXTEND_R2]}).status_code == 200
    bad = client.post("/api/simulations", json={"changes": [_add("R2", "MUS", "TEC", 5)]})
    assert bad.status_code == 422 and "stops at neither" in bad.json()["detail"]


class _FakeModel:
    def __init__(self, answer: dict[str, Any]) -> None:
        self.answer = json.dumps(answer)

    def complete_json(self, system_prompt: str, user_text: str, schema: dict) -> str:
        return self.answer


def _ai(*changes: dict[str, Any]) -> dict[str, Any]:
    return {"status": "ok", "changes": list(changes), "message": "Understood."}


def test_prompt_lists_the_stops_of_each_route(sample: nx.DiGraph) -> None:
    prompt = build_system_prompt(sample)
    assert "- R2: East–West, a bus every 10 min; stops: CEN, EST, LIB, RIV, WST" in prompt
    assert "add_connection" in prompt and "never guess" in prompt


def test_ai_add_connection(sample: nx.DiGraph) -> None:
    ok = interpret("extend R2 to Tech Park, 5 min", sample, _FakeModel(_ai(EXTEND_R2)))
    assert ok.status == "ok" and ok.changes[0].type == "add_connection"
    off_route = interpret("link", sample, _FakeModel(_ai(_add("R2", "MUS", "TEC", 5))))
    assert off_route.status == "unclear" and "stops at neither" in off_route.message
