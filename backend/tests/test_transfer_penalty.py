"""Transfer penalty: minutes added per change of bus (Day 7, part 3).

Hand-calculated expectations on small networks, plus checks on the sample
network. Penalty 0 must reproduce the free-transfer model (covered by the
other test files, which run at 0).
"""

from itertools import pairwise, permutations
from typing import Any

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.main import app
from app.models import Connection, Stop
from app.schemas.scenario import Scenario
from app.services.journey_service import plan_journey
from app.services.network_service import build_graph, build_graph_from_db
from app.services.route_graph import build_route_graph, travel_times_from
from app.services.simulation_service import simulate


def _network(routes: dict[str, list[tuple[str, float]]]) -> nx.DiGraph:
    """Two-way network from {route: [(stop, minutes_to_next), ...]}."""
    stop_ids = sorted({stop for path in routes.values() for stop, _ in path})
    connections = []
    for route_id, path in routes.items():
        for (a, minutes), (b, _) in pairwise(path):
            connections += [
                Connection(route_id=route_id, from_stop_id=a, to_stop_id=b, travel_time_min=minutes),
                Connection(route_id=route_id, from_stop_id=b, to_stop_id=a, travel_time_min=minutes),
            ]
    return build_graph([Stop(id=s, name=s, lat=0.0, lon=0.0) for s in stop_ids], connections)


def _scenario(*changes: dict[str, Any]) -> Scenario:
    return Scenario.model_validate({"changes": list(changes)})


@pytest.fixture
def cross() -> nx.DiGraph:
    """R1: A-X-B and R2: C-X-D, 1 min per stretch, crossing at X."""
    return _network({"R1": [("A", 1), ("X", 1), ("B", 0)], "R2": [("C", 1), ("X", 1), ("D", 0)]})


@pytest.fixture
def sample(db: Session) -> nx.DiGraph:
    return build_graph_from_db(db)


# --- Journey times ---------------------------------------------------------------------

def test_one_change_of_bus_adds_the_penalty_once(cross: nx.DiGraph) -> None:
    assert travel_times_from(build_route_graph(cross, 0), "A")["D"] == 2  # 1 + 1
    assert travel_times_from(build_route_graph(cross, 5), "A")["D"] == 7  # 1 + 1 + 5


def test_first_boarding_is_free(cross: nx.DiGraph) -> None:
    assert travel_times_from(build_route_graph(cross, 5), "A")["B"] == 2  # R1 only


def test_staying_on_the_bus_beats_a_faster_route_with_a_change() -> None:
    # R1: A-B-C, 5 + 5 = 10 min. R2 runs B-C in 1 min, but needs a change at B.
    graph = _network({"R1": [("A", 5), ("B", 5), ("C", 0)], "R2": [("B", 1), ("C", 0)]})

    assert travel_times_from(build_route_graph(graph, 0), "A")["C"] == 6  # 5 + 1, change free
    assert travel_times_from(build_route_graph(graph, 5), "A")["C"] == 10  # stay on R1

    plan = plan_journey(graph, "A", "C", transfer_penalty_min=5)
    assert plan is not None
    assert [leg.route_id for leg in plan.legs] == ["R1"]


def test_one_stop_hop_on_another_route_disappears(sample: nx.DiGraph) -> None:
    """Without a penalty, NTH -> STH hops onto R4 for MKT-CEN (1 min faster)."""
    free = plan_journey(sample, "NTH", "STH", transfer_penalty_min=0)
    penalised = plan_journey(sample, "NTH", "STH", transfer_penalty_min=5)

    assert free is not None and penalised is not None
    assert (free.travel_time_min, [leg.route_id for leg in free.legs]) == (18.0, ["R1", "R4", "R1"])
    assert (penalised.travel_time_min, [leg.route_id for leg in penalised.legs]) == (19.0, ["R1"])


def test_negative_penalty_is_rejected(cross: nx.DiGraph) -> None:
    with pytest.raises(ValueError):
        build_route_graph(cross, -1)


# --- Breakdown ---------------------------------------------------------------------------

def test_journey_time_is_bus_time_plus_penalty_per_change(sample: nx.DiGraph) -> None:
    for origin, destination in permutations(sorted(sample.nodes), 2):
        plan = plan_journey(sample, origin, destination, transfer_penalty_min=5)
        assert plan is not None
        assert plan.transfers == len(plan.legs) - 1
        assert plan.transfer_penalty_min == 5
        assert plan.travel_time_min == pytest.approx(plan.in_vehicle_min + 5 * plan.transfers, abs=0.05)
        assert plan.in_vehicle_min == pytest.approx(
            sum(leg.travel_time_min for leg in plan.legs), abs=0.05 * len(plan.legs))


# --- Simulation -------------------------------------------------------------------------

def test_closing_the_only_transfer_stop_still_blocks_changes(cross: nx.DiGraph) -> None:
    summary = simulate(cross, _scenario({"type": "close_stop", "stop_id": "X"}), 5).summary

    assert (summary.unchanged, summary.impossible) == (4, 8)
    assert summary.transfer_penalty_min == 5


def test_penalty_raises_baseline_times(sample: nx.DiGraph) -> None:
    scenario = _scenario({"type": "close_stop", "stop_id": "CEN"})
    free = simulate(sample, scenario, 0).summary
    penalised = simulate(sample, scenario, 5).summary

    assert free.transfer_penalty_min == 0
    assert penalised.average_time_before_min is not None
    assert free.average_time_before_min is not None
    assert penalised.average_time_before_min > free.average_time_before_min


# --- Configuration and API -------------------------------------------------------------

def test_setting_defaults_to_5_and_is_bounded() -> None:
    assert Settings(_env_file=None).transfer_penalty_min == 5  # type: ignore[call-arg]
    for invalid in (-1, 61):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, transfer_penalty_min=invalid)  # type: ignore[call-arg]


def _use_penalty(minutes: float) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, groq_api_key=None, transfer_penalty_min=minutes  # type: ignore[call-arg]
    )


def test_api_uses_the_configured_penalty(client: TestClient) -> None:
    _use_penalty(5)

    simulation = client.post("/api/simulations", json={"changes": [{"type": "close_stop", "stop_id": "CEN"}]})
    journey = client.post("/api/journeys", json={"origin_id": "NTH", "destination_id": "STH"})

    assert simulation.status_code == journey.status_code == 200
    assert simulation.json()["summary"]["transfer_penalty_min"] == 5
    before = journey.json()["before"]
    assert (before["travel_time_min"], before["transfers"], before["transfer_penalty_min"]) == (19.0, 0, 5)
