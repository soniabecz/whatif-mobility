"""Scenario type "add stop" (Day 11, part 2).

A new stop is inserted into one route between two consecutive stops; the
route's buses then stop there. Journeys to or from new stops have no
"before" and are reported separately (summary.new_stops).
"""

import copy
from typing import Any

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models import Connection, Route, Stop
from app.schemas.journey import JourneyRequest
from app.schemas.scenario import AddStop, Scenario
from app.services.ai_service import build_system_prompt
from app.services.journey_service import JourneyError, compare_journey
from app.services.network_service import build_graph, build_graph_from_db
from app.services.simulation_service import ScenarioError, apply_scenario, simulate
from app.services.walking import WalkingModel

M_PER_DEG = 6_371_000 * 3.141592653589793 / 180


def _lat(metres: float) -> float:
    return metres / M_PER_DEG


def _network(links: list[tuple[str, str, str, float]], positions: dict[str, float]) -> nx.DiGraph:
    """Two-way links (route, a, b, minutes); stops due north at `positions` metres."""
    stops = [Stop(id=s, name=f"Stop {s}", lat=_lat(m), lon=0.0, activity=1) for s, m in positions.items()]
    connections = []
    for route, a, b, minutes in links:
        connections += [
            Connection(route_id=route, from_stop_id=a, to_stop_id=b, travel_time_min=minutes),
            Connection(route_id=route, from_stop_id=b, to_stop_id=a, travel_time_min=minutes),
        ]
    routes = {route for route, *_ in links}
    return build_graph(stops, connections, [Route(id=r, name=r, color="#000", headway_min=10) for r in routes])


# A -R1 4- B -R2 5- C, stops 1,000 m apart.
NET = _network([("R1", "A", "B", 4), ("R2", "B", "C", 5)], {"A": 0, "B": 1000, "C": 2000})


def _stop(**overrides: Any) -> dict[str, Any]:
    change = {"type": "add_stop", "stop_id": "N1", "name": "New Square", "lat": _lat(500), "lon": 0.0,
              "route_id": "R1", "from_stop_id": "A", "to_stop_id": "B",
              "time_from_min": 2, "time_to_min": 3}
    return {**change, **overrides}


def _scenario(*changes: dict[str, Any]) -> Scenario:
    return Scenario.model_validate({"changes": list(changes)})


def _times(result: Any) -> dict[tuple[str, str], tuple[float, float | None, str]]:
    return {(j.origin_id, j.destination_id): (j.time_before_min, j.time_after_min, j.status)
            for j in result.changed_journeys}


# --- Schema --------------------------------------------------------------------------------

def test_schema() -> None:
    assert isinstance(_scenario(_stop()).changes[0], AddStop)
    for invalid in (_stop(stop_id="A"), _stop(to_stop_id="A"), _stop(name="  "), _stop(lat=91),
                    _stop(time_to_min=0), {**_stop(), "activity": 3}):
        with pytest.raises(ValidationError):
            _scenario(invalid)


# --- Engine --------------------------------------------------------------------------------

def test_the_route_now_stops_at_the_new_stop_in_both_directions() -> None:
    graph, _ = apply_scenario(NET, _scenario(_stop()))
    assert not graph.has_edge(("A", "R1"), ("B", "R1"))
    assert graph.edges[("A", "R1"), ("N1", "R1")]["weight"] == 2
    assert graph.edges[("N1", "R1"), ("B", "R1")]["weight"] == 3
    assert graph.edges[("B", "R1"), ("N1", "R1")]["weight"] == 3
    assert graph.edges[("N1", "R1"), ("A", "R1")]["weight"] == 2
    assert graph.nodes["N1"]["name"] == "New Square"


def test_existing_journeys_are_compared_as_usual() -> None:
    times = _times(simulate(NET, _scenario(_stop())))
    assert times[("A", "B")] == (4.0, 5.0, "slower")  # 2 + 3 instead of 4
    assert times[("C", "A")] == (9.0, 10.0, "slower")


def test_other_routes_on_the_same_street_are_untouched() -> None:
    shared = _network([("R1", "A", "B", 4), ("R3", "A", "B", 4)], {"A": 0, "B": 1000})
    result = simulate(shared, _scenario(_stop()))
    assert result.changed_journeys == []  # R3 still runs A-B in 4 min


def test_new_stop_journeys_are_reported_separately() -> None:
    summary = simulate(NET, _scenario(_stop())).summary
    assert summary.total_journeys == 6  # the baseline's journeys only
    new = summary.new_stops
    assert new is not None
    assert (new.stop_ids, new.journeys, new.possible) == (["N1"], 6, 6)
    # N1->A 2, N1->B 3, N1->C 8 and the same back: average 13 * 2 / 6.
    assert new.average_time_min == 4.3
    assert simulate(NET, _scenario({"type": "close_stop", "stop_id": "C"})).summary.new_stops is None


def test_one_way_route_gets_the_stop_in_its_direction_only() -> None:
    one_way = build_graph(
        [Stop(id=s, name=s, lat=0.0, lon=0.0, activity=1) for s in ("A", "B")],
        [Connection(route_id="R1", from_stop_id="A", to_stop_id="B", travel_time_min=4)],
        [Route(id="R1", name="R1", color="#000", headway_min=10)],
    )
    graph, _ = apply_scenario(one_way, _scenario(_stop()))
    assert graph.has_edge(("A", "R1"), ("N1", "R1")) and not graph.has_edge(("B", "R1"), ("N1", "R1"))
    with pytest.raises(ScenarioError, match="does not run directly from 'B' to 'A'"):
        apply_scenario(one_way, _scenario(_stop(from_stop_id="B", to_stop_id="A")))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_stop(stop_id="C"), "stop id 'C' is already used"),
        (_stop(name="Stop C"), "a stop called 'Stop C' already exists"),
        (_stop(to_stop_id="C"), "route 'R1' does not run directly from 'A' to 'C'"),
        (_stop(route_id="R9"), "unknown route 'R9'"),
        (_stop(from_stop_id="X"), "unknown stop 'X'"),
    ],
)
def test_invalid_new_stops_are_rejected(change: dict[str, Any], message: str) -> None:
    with pytest.raises(ScenarioError, match=r"Change 1 \(add_stop\): " + message):
        apply_scenario(NET, _scenario(change))


def test_adding_the_same_stop_twice_is_rejected() -> None:
    with pytest.raises(ScenarioError, match=r"Change 2 \(add_stop\): stop id 'N1' is already used"):
        apply_scenario(NET, _scenario(_stop(), _stop(name="Other", to_stop_id="B")))


def test_later_changes_apply_to_the_new_stop() -> None:
    graph, _ = apply_scenario(
        NET,
        _scenario(_stop(), {"type": "change_frequency", "route_id": "R1", "headway_min": 4}),
        include_waiting=True,
    )
    assert graph.edges["N1", ("N1", "R1")]["wait_min"] == 2
    closed = simulate(NET, _scenario(_stop(), {"type": "close_stop", "stop_id": "N1"}))
    assert closed.summary.new_stops is None


def test_walking_from_a_closed_stop_can_use_a_new_stop() -> None:
    # A closed; N1 is 500 m away (650 m walking), B 1,300 m (out of reach).
    walk = WalkingModel(speed_kmh=6, max_walk_m=1000)
    with_new = simulate(NET, _scenario(_stop(), {"type": "close_stop", "stop_id": "A"}), walking=walk)
    without = simulate(NET, _scenario({"type": "close_stop", "stop_id": "A"}), walking=walk)
    assert _times(with_new)[("A", "C")] == (9.0, 6.5 + 3 + 5, "slower")  # walk to N1, R1, R2
    assert _times(without)[("A", "C")][2] == "impossible"


def test_explorer_new_stop_as_origin() -> None:
    request = JourneyRequest(origin_id="N1", destination_id="C", changes=[_stop()])
    comparison = compare_journey(NET, request)
    assert (comparison.status, comparison.before) == ("new", None)
    assert comparison.after is not None
    assert [(leg.route_id, leg.stop_ids) for leg in comparison.after.legs] == [
        ("R1", ["N1", "B"]), ("R2", ["B", "C"])
    ]
    with pytest.raises(JourneyError, match="Unknown stop 'N1'"):
        compare_journey(NET, JourneyRequest(origin_id="N1", destination_id="C"))


def test_baseline_is_never_modified() -> None:
    snapshot = copy.deepcopy(NET)
    simulate(NET, _scenario(_stop()), 2.0, True, WalkingModel(5, 1000))
    assert nx.utils.graphs_equal(NET, snapshot)
    assert dict(NET.nodes(data=True)) == dict(snapshot.nodes(data=True))


# --- Sample network, API, AI ---------------------------------------------------------------

@pytest.fixture
def sample(db: Session) -> nx.DiGraph:
    return build_graph_from_db(db)


OLD_MARKET = {"type": "add_stop", "stop_id": "N1", "name": "Old Market", "lat": 50.0644, "lon": 19.9366,
              "route_id": "R1", "from_stop_id": "MKT", "to_stop_id": "UNI",
              "time_from_min": 1.5, "time_to_min": 2}


def test_sample_new_stop(sample: nx.DiGraph) -> None:
    closed_only = WalkingModel(5, 1000, between_open_stops=False)  # no walking between open stops
    summary = simulate(sample, _scenario(OLD_MARKET), 2.0, True, closed_only).summary
    assert summary.total_journeys == 240
    assert summary.new_stops is not None
    assert (summary.new_stops.journeys, summary.new_stops.possible) == (32, 32)
    assert summary.slower > 0 and summary.faster == 0  # 1.5 + 2 > MKT-UNI's 3 min


def test_a_new_stop_is_a_new_place_to_walk_to(sample: nx.DiGraph) -> None:
    # Library is 11.3 min on foot from Old Market (10.0 to Central): walking to the
    # new stop and taking R1 beats walking to Central for some journeys.
    result = simulate(sample, _scenario(OLD_MARKET), 2.0, True, WalkingModel(5, 1000))
    times = {(j.origin_id, j.destination_id): (j.time_before_min, j.time_after_min, j.status)
             for j in result.changed_journeys}
    assert times[("LIB", "MKT")] == (18.0, 17.8, "faster")
    assert times[("MKT", "LIB")] == (18.0, 17.8, "faster")


def test_api(client: TestClient) -> None:
    simulation = client.post("/api/simulations", json={"changes": [OLD_MARKET]})
    assert simulation.status_code == 200
    assert simulation.json()["summary"]["new_stops"]["stop_ids"] == ["N1"]
    journey = client.post(
        "/api/journeys", json={"origin_id": "N1", "destination_id": "AIR", "changes": [OLD_MARKET]}
    )
    assert journey.status_code == 200 and journey.json()["status"] == "new"
    bad = client.post("/api/simulations", json={"changes": [{**OLD_MARKET, "to_stop_id": "HOS"}]})
    assert bad.status_code == 422 and "does not run directly" in bad.json()["detail"]


def test_ai_sends_new_stops_to_the_form(sample: nx.DiGraph) -> None:
    prompt = build_system_prompt(sample)
    assert "New stops cannot be added here" in prompt and '"Add stop" tab' in prompt
