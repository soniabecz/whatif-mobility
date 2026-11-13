"""Scenario type "add route" (Day 11, part 3).

A new bus line through existing (or earlier added) stops, in order, with a
travel time per stretch and a headway given by the user. It may be a loop and
run one way or both ways. It can only make journeys faster or newly possible.
"""

import copy
import json
from typing import Any

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models import Connection, Route, Stop
from app.schemas.journey import JourneyRequest
from app.schemas.scenario import AddRoute, Scenario
from app.services.ai_service import build_system_prompt, interpret
from app.services.journey_service import compare_journey
from app.services.network_service import build_graph, build_graph_from_db
from app.services.simulation_service import ScenarioError, apply_scenario, simulate
from app.services.walking import WalkingModel


def _network(links: list[tuple[str, str, str, float]], stops: list[str]) -> nx.DiGraph:
    """Two-way links (route, a, b, minutes)."""
    connections = []
    for route, a, b, minutes in links:
        connections += [
            Connection(route_id=route, from_stop_id=a, to_stop_id=b, travel_time_min=minutes),
            Connection(route_id=route, from_stop_id=b, to_stop_id=a, travel_time_min=minutes),
        ]
    routes = sorted({route for route, *_ in links})
    return build_graph(
        [Stop(id=s, name=f"Stop {s}", lat=0.0, lon=0.0, activity=1) for s in stops],
        connections,
        [Route(id=r, name=f"Line {r}", color="#000000", headway_min=10) for r in routes],
    )


# A -R1 4- B -R2 5- C, and D -R3 2- E (not connected to the rest).
NET = _network([("R1", "A", "B", 4), ("R2", "B", "C", 5), ("R3", "D", "E", 2)], ["A", "B", "C", "D", "E"])


def _route(**overrides: Any) -> dict[str, Any]:
    change = {"type": "add_route", "route_id": "R5", "name": "Cross Town", "color": "#7c3aed",
              "headway_min": 12, "stop_ids": ["A", "C"], "travel_times_min": [6]}
    return {**change, **overrides}


def _scenario(*changes: dict[str, Any]) -> Scenario:
    return Scenario.model_validate({"changes": list(changes)})


def _times(result: Any) -> dict[tuple[str, str], tuple[float, float | None, str]]:
    return {(j.origin_id, j.destination_id): (j.time_before_min, j.time_after_min, j.status)
            for j in result.changed_journeys}


# --- Schema --------------------------------------------------------------------------------

def test_schema() -> None:
    change = _scenario(_route()).changes[0]
    assert isinstance(change, AddRoute)
    assert (change.is_loop, change.both_directions) == (False, True)
    loop = _scenario(_route(stop_ids=["A", "B", "C"], travel_times_min=[1, 2, 3], is_loop=True))
    assert loop.changes[0].stretches() == [("A", "B", 1), ("B", "C", 2), ("C", "A", 3)]  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"stop_ids": ["A", "C", "A"], "travel_times_min": [1, 2]}, "same stop twice"),
        ({"stop_ids": ["A", "B", "C"]}, "3 stops need 2 travel times, got 1"),
        ({"stop_ids": ["A", "B", "C"], "travel_times_min": [1, 2], "is_loop": True},
         "3 stops need 3 travel times .a loop includes the way back"),
        ({"travel_times_min": [], "is_loop": True}, "a loop needs at least 3 stops"),
        ({"stop_ids": ["A"], "travel_times_min": []}, "at least 2 items"),
        ({"travel_times_min": [0]}, "greater than 0"),
        ({"headway_min": 0.5}, "greater than or equal to 1"),
        ({"color": "purple"}, "should match pattern"),
        ({"name": "  "}, "needs a name"),
        ({"stop_ids": [f"S{i}" for i in range(31)], "travel_times_min": [1] * 30}, "at most 30"),
        ({"activity": 2}, "Extra inputs"),
    ],
)
def test_schema_rejects(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _scenario(_route(**overrides))


# --- Engine --------------------------------------------------------------------------------

def test_the_new_route_runs_both_ways_by_default() -> None:
    graph, _ = apply_scenario(NET, _scenario(_route()))
    assert graph.edges[("A", "R5"), ("C", "R5")]["weight"] == 6
    assert graph.edges[("C", "R5"), ("A", "R5")]["weight"] == 6
    assert graph.graph["route_names"]["R5"] == "Cross Town"
    assert "R5" not in NET.graph["headways"]


def test_one_way_loop() -> None:
    change = _route(stop_ids=["A", "B", "C"], travel_times_min=[1, 2, 3], is_loop=True, both_directions=False)
    graph, _ = apply_scenario(NET, _scenario(change))
    rides = {(u[0], v[0]) for u, v, d in graph.edges(data=True) if d.get("route_id") == "R5" and d["kind"] == "ride"}
    assert rides == {("A", "B"), ("B", "C"), ("C", "A")}


def test_journeys_get_faster() -> None:
    result = simulate(NET, _scenario(_route()))
    times = _times(result)
    assert times[("A", "C")] == (9.0, 6.0, "faster")
    assert times[("C", "A")] == (9.0, 6.0, "faster")
    assert (result.summary.slower, result.summary.impossible, result.summary.faster) == (0, 0, 2)
    assert result.summary.new_stops is None  # no new stops, only a new route


def test_waiting_uses_the_new_headway() -> None:
    graph, _ = apply_scenario(NET, _scenario(_route()), include_waiting=True)
    assert graph.edges["A", ("A", "R5")]["wait_min"] == 6
    # With waiting (5 min on R1/R2) and a penalty of 2: A->C was 4+5+2*5+2 = 21, now 6+6 = 12.
    result = simulate(NET, _scenario(_route()), transfer_penalty_min=2, include_waiting=True)
    assert _times(result)[("A", "C")] == (21.0, 12.0, "faster")


def test_a_new_route_can_make_journeys_possible() -> None:
    summary = simulate(NET, _scenario(_route(stop_ids=["C", "D"], travel_times_min=[3]))).summary
    # A, B, C <-> D, E: 12 journeys were impossible before.
    assert summary.newly_possible == 12
    one_way = simulate(NET, _scenario(_route(stop_ids=["C", "D"], travel_times_min=[3], both_directions=False)))
    assert one_way.summary.newly_possible == 6


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_route(route_id="R2"), "route id 'R2' is already used"),
        (_route(name="Line R1"), "a route called 'Line R1' already exists"),
        (_route(stop_ids=["A", "X"]), "unknown stop 'X'"),
    ],
)
def test_invalid_routes_are_rejected(change: dict[str, Any], message: str) -> None:
    with pytest.raises(ScenarioError, match=r"Change 1 \(add_route\): " + message):
        apply_scenario(NET, _scenario(change))


def test_closed_stops_and_repeated_routes_are_rejected() -> None:
    with pytest.raises(ScenarioError, match=r"Change 2 \(add_route\): stop 'C' is already closed"):
        apply_scenario(NET, _scenario({"type": "close_stop", "stop_id": "C"}, _route()))
    with pytest.raises(ScenarioError, match=r"Change 2 \(add_route\): route id 'R5' is already used"):
        apply_scenario(NET, _scenario(_route(), _route(name="Other")))
    with pytest.raises(ScenarioError, match=r"Change 2 \(add_route\): a route called 'Cross Town'"):
        apply_scenario(NET, _scenario(_route(), _route(route_id="R6")))


def test_a_new_route_may_use_an_added_stop() -> None:
    new_stop = {"type": "add_stop", "stop_id": "N1", "name": "New Square", "lat": 0.0, "lon": 0.0,
                "route_id": "R1", "from_stop_id": "A", "to_stop_id": "B",
                "time_from_min": 2, "time_to_min": 3}
    graph, _ = apply_scenario(NET, _scenario(new_stop, _route(stop_ids=["N1", "C"], travel_times_min=[4])))
    assert graph.has_edge(("N1", "R5"), ("C", "R5"))
    result = simulate(NET, _scenario(new_stop, _route(stop_ids=["N1", "C"], travel_times_min=[4])))
    assert _times(result)[("A", "C")] == (9.0, 6.0, "faster")  # A -R1 2- N1 -R5 4- C


def test_later_changes_apply_to_the_new_route() -> None:
    graph, closed = apply_scenario(
        NET,
        _scenario(
            _route(stop_ids=["A", "C"], travel_times_min=[6]),
            {"type": "change_frequency", "route_id": "R5", "headway_min": 4},
            {"type": "add_connection", "route_id": "R5", "from_stop_id": "C", "to_stop_id": "D",
             "travel_time_min": 3},
            {"type": "add_stop", "stop_id": "N1", "name": "Midway", "lat": 0.0, "lon": 0.0,
             "route_id": "R5", "from_stop_id": "A", "to_stop_id": "C", "time_from_min": 2, "time_to_min": 3},
            {"type": "close_stop", "stop_id": "C"},
        ),
        include_waiting=True,
    )
    assert graph.edges["A", ("A", "R5")]["wait_min"] == 2
    assert graph.has_edge(("N1", "R5"), ("C", "R5")) and graph.has_edge(("C", "R5"), ("D", "R5"))
    assert not graph.has_edge(("A", "R5"), ("C", "R5"))
    assert closed == {"C"}


def test_explorer_shows_the_new_route() -> None:
    request = JourneyRequest(origin_id="A", destination_id="C", changes=[_route()])
    comparison = compare_journey(NET, request)
    assert comparison.status == "faster"
    assert comparison.after is not None
    assert [(leg.route_id, leg.stop_ids) for leg in comparison.after.legs] == [("R5", ["A", "C"])]


def test_baseline_is_never_modified() -> None:
    snapshot = copy.deepcopy(NET)
    simulate(NET, _scenario(_route()), 2.0, True, WalkingModel(5, 1000))
    assert nx.utils.graphs_equal(NET, snapshot)
    assert NET.graph == snapshot.graph


# --- Sample network, API, AI ---------------------------------------------------------------

@pytest.fixture
def sample(db: Session) -> nx.DiGraph:
    return build_graph_from_db(db)


CROSS_TOWN = {"type": "add_route", "route_id": "R5", "name": "Cross Town", "color": "#7c3aed",
              "headway_min": 12, "stop_ids": ["OLD", "MKT", "RIV"], "travel_times_min": [3, 4]}


def test_api(client: TestClient) -> None:
    response = client.post("/api/simulations", json={"changes": [CROSS_TOWN]})
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["slower"] == 0 and summary["impossible"] == 0 and summary["faster"] > 0
    changed = {(j["origin_id"], j["destination_id"]): j for j in response.json()["changed_journeys"]}
    # Before: OLD -R3- UNI -R3- MUS -R3- RIV = 3 + 3 + 4 = 10 min (penalty 0, no waiting).
    assert (changed["OLD", "RIV"]["time_before_min"], changed["OLD", "RIV"]["time_after_min"]) == (10, 7)
    bad = client.post("/api/simulations", json={"changes": [{**CROSS_TOWN, "name": "Ring"}]})
    assert bad.status_code == 422 and "a route called 'Ring' already exists" in bad.json()["detail"]


class _FakeModel:
    def __init__(self, answer: dict[str, Any]) -> None:
        self.answer = json.dumps(answer)

    def complete_json(self, system_prompt: str, user_text: str, schema: dict) -> str:
        return self.answer


def _ai(*changes: dict[str, Any]) -> dict[str, Any]:
    return {"status": "ok", "changes": list(changes), "message": "Understood."}


AI_ROUTE = {**CROSS_TOWN, "is_loop": False, "both_directions": True}


def test_prompt_offers_the_next_id_and_free_colours(sample: nx.DiGraph) -> None:
    prompt = build_system_prompt(sample)
    assert "NEW ROUTES: use route_id R5 " in prompt
    assert "#7c3aed, #db2777, #0d9488, #92400e, #ca8a04, #475569" in prompt
    assert "add_route" in prompt and "EVERY travel time and the headway" in prompt


def test_ai_add_route(sample: nx.DiGraph) -> None:
    ok = interpret("new line Old Town - Market - Riverside, 3 and 4 min, every 12 min", sample,
                   _FakeModel(_ai(AI_ROUTE)))
    assert ok.status == "ok" and isinstance(ok.changes[0], AddRoute)
    missing_time = interpret("...", sample, _FakeModel(_ai({**AI_ROUTE, "travel_times_min": [3]})))
    assert missing_time.status == "unclear" and "need 2 travel times" in missing_time.message
    taken = interpret("...", sample, _FakeModel(_ai({**AI_ROUTE, "route_id": "R3"})))
    assert taken.status == "unclear" and "already used" in taken.message
