"""Waiting time from route frequencies (Day 10, part 1).

Passengers arrive at random, so at every boarding (the first included) they
wait half the route's headway. The transfer penalty is added per change of
bus on top. Hand-calculated expectations on small networks, plus checks on
the sample network. Waiting off must reproduce the earlier model (checked
in full against the pre-Day-10 engine; the other test files run with it off).
"""

from itertools import pairwise, permutations

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.main import app
from app.models import Connection, Route, Stop
from app.schemas.journey import JourneyRequest
from app.schemas.scenario import Scenario
from app.services.journey_service import compare_journey, plan_journey
from app.services.network_service import build_graph, build_graph_from_db
from app.services.route_graph import build_route_graph, travel_times_from
from app.services.simulation_service import simulate


def _network(
    routes: dict[str, list[tuple[str, float]]], headways: dict[str, float]
) -> nx.DiGraph:
    """Two-way network from {route: [(stop, minutes_to_next), ...]} and headways."""
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
        [Route(id=r, name=r, color="#000000", headway_min=h) for r, h in headways.items()],
    )


# A -R1 3 min- B -R2 4 min- C ; R1 every 10 min, R2 every 20 min.
LINE = _network({"R1": [("A", 3), ("B", 0)], "R2": [("B", 4), ("C", 0)]}, {"R1": 10, "R2": 20})


def test_first_boarding_waits_half_the_headway() -> None:
    times = travel_times_from(build_route_graph(LINE, 2.0, include_waiting=True), "A")
    assert times["B"] == 5 + 3  # wait 10/2, ride 3; no change of bus, no penalty


def test_each_change_adds_the_next_wait_and_one_penalty() -> None:
    times = travel_times_from(build_route_graph(LINE, 2.0, include_waiting=True), "A")
    assert times["C"] == 5 + 3 + 2 + 10 + 4  # wait R1, ride, penalty, wait R2, ride


def test_explorer_breaks_the_time_down() -> None:
    plan = plan_journey(LINE, "A", "C", 2.0, include_waiting=True)
    assert plan is not None
    assert (plan.travel_time_min, plan.in_vehicle_min, plan.wait_min, plan.transfers) == (24, 7, 15, 1)
    assert plan.travel_time_min == plan.in_vehicle_min + plan.wait_min + plan.transfers * 2
    assert [(leg.route_id, leg.wait_min) for leg in plan.legs] == [("R1", 5), ("R2", 10)]


def test_without_waiting_wait_is_zero() -> None:
    plan = plan_journey(LINE, "A", "C", 2.0, include_waiting=False)
    assert plan is not None
    assert (plan.travel_time_min, plan.wait_min) == (3 + 2 + 4, 0)


@pytest.mark.parametrize(("direct_headway", "expected_routes"), [(60, ["R1", "R2"]), (4, ["R3"])])
def test_frequency_decides_the_route(direct_headway: float, expected_routes: list[str]) -> None:
    # Direct R3 A->C takes 10 min. Rarely served (wait 30): changing via B
    # (24 min) wins. Frequent (wait 2): direct (12 min) wins.
    network = _network(
        {"R1": [("A", 3), ("B", 0)], "R2": [("B", 4), ("C", 0)], "R3": [("A", 10), ("C", 0)]},
        {"R1": 10, "R2": 20, "R3": direct_headway},
    )
    plan = plan_journey(network, "A", "C", 2.0, include_waiting=True)
    assert plan is not None
    assert [leg.route_id for leg in plan.legs] == expected_routes


def test_waiting_needs_a_headway_for_every_route() -> None:
    no_headways = _network({"R1": [("A", 3), ("B", 0)]}, {})
    with pytest.raises(ValueError, match="no headway for route 'R1'"):
        build_route_graph(no_headways, 0.0, include_waiting=True)
    build_route_graph(no_headways, 0.0, include_waiting=False)  # fine without waiting


# --- Sample network ------------------------------------------------------------------------

@pytest.fixture
def sample(db: Session) -> nx.DiGraph:
    return build_graph_from_db(db)


def test_sample_routes_have_the_agreed_headways(sample: nx.DiGraph) -> None:
    assert sample.graph["headways"] == {"R1": 10, "R2": 10, "R3": 15, "R4": 20}


def test_breakdown_adds_up_for_every_sample_journey(sample: nx.DiGraph) -> None:
    for origin, destination in permutations(sorted(sample.nodes), 2):
        plan = plan_journey(sample, origin, destination, 2.0, include_waiting=True)
        assert plan is not None
        parts = plan.in_vehicle_min + plan.wait_min + plan.transfers * plan.transfer_penalty_min
        assert plan.travel_time_min == pytest.approx(parts, abs=0.15), (origin, destination)
        assert plan.wait_min >= 5  # at least the first wait (shortest headway 10)


def test_waiting_makes_every_journey_longer(sample: nx.DiGraph) -> None:
    for origin in sorted(sample.nodes):
        without = travel_times_from(build_route_graph(sample, 2.0, include_waiting=False), origin)
        with_wait = travel_times_from(build_route_graph(sample, 2.0, include_waiting=True), origin)
        for destination, minutes in without.items():
            assert with_wait[destination] >= minutes + 5 - 1e-9, (origin, destination)


def test_simulation_reports_the_model(sample: nx.DiGraph) -> None:
    scenario = Scenario.model_validate({"changes": [{"type": "close_stop", "stop_id": "CEN"}]})
    summary = simulate(sample, scenario, 2.0, include_waiting=True).summary
    assert (summary.transfer_penalty_min, summary.include_waiting) == (2.0, True)


def test_baseline_is_never_modified(sample: nx.DiGraph) -> None:
    import copy

    snapshot = copy.deepcopy(sample)
    request = JourneyRequest(
        origin_id="NTH", destination_id="AIR", changes=[{"type": "close_stop", "stop_id": "CEN"}]
    )
    compare_journey(sample, request, 2.0, include_waiting=True)
    simulate(sample, Scenario(changes=request.changes), 2.0, include_waiting=True)
    assert nx.utils.graphs_equal(sample, snapshot)
    assert sample.graph == snapshot.graph


# --- Settings and API ----------------------------------------------------------------------

def test_waiting_is_on_by_default() -> None:
    assert Settings(_env_file=None).include_waiting is True  # type: ignore[call-arg]


def test_api_uses_the_configured_model(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,  # type: ignore[call-arg]
        groq_api_key=None,
        transfer_penalty_min=2.0,
        include_waiting=True,
    )
    simulation = client.post(
        "/api/simulations", json={"changes": [{"type": "close_stop", "stop_id": "CEN"}]}
    )
    journey = client.post("/api/journeys", json={"origin_id": "NTH", "destination_id": "STH"})
    routes = client.get("/api/routes")

    assert simulation.status_code == journey.status_code == routes.status_code == 200
    assert simulation.json()["summary"]["include_waiting"] is True
    before = journey.json()["before"]
    # NTH -> STH is one ride on R1 (19 min) after waiting 10 / 2.
    assert (before["travel_time_min"], before["in_vehicle_min"], before["wait_min"]) == (24, 19, 5)
    assert {r["id"]: r["headway_min"] for r in routes.json()} == {"R1": 10, "R2": 10, "R3": 15, "R4": 20}
