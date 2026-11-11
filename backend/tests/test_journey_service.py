"""Journey explorer: legs, statuses, reasons, and agreement with the simulation."""

import copy
from itertools import pairwise, permutations
from typing import Any

import networkx as nx
import pytest
from sqlalchemy.orm import Session

from app.models import Connection, Stop
from app.schemas.journey import JourneyRequest
from app.schemas.scenario import Scenario
from app.services.journey_service import JourneyError, compare_journey, plan_journey
from app.services.network_service import build_graph, build_graph_from_db
from app.services.simulation_service import ScenarioError, apply_scenario, simulate


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


def _request(origin: str, destination: str, *changes: dict[str, Any]) -> JourneyRequest:
    return JourneyRequest.model_validate(
        {"origin_id": origin, "destination_id": destination, "changes": list(changes)}
    )


@pytest.fixture
def sample(db: Session) -> nx.DiGraph:
    return build_graph_from_db(db)


# --- Legs ---------------------------------------------------------------------------

def test_single_route_journey_is_one_leg() -> None:
    graph = _network({"R1": [("A", 2), ("B", 3), ("C", 0)]})

    plan = plan_journey(graph, "A", "C")

    assert plan is not None
    assert plan.travel_time_min == 5.0
    assert [(leg.route_id, leg.stop_ids, leg.travel_time_min) for leg in plan.legs] == [
        ("R1", ["A", "B", "C"], 5.0)
    ]


def test_change_of_route_starts_a_new_leg() -> None:
    graph = _network({
        "R1": [("A", 1), ("X", 1), ("B", 0)],
        "R2": [("C", 1), ("X", 1), ("D", 0)],
    })

    plan = plan_journey(graph, "A", "D")

    assert plan is not None
    assert [(leg.route_id, leg.stop_ids) for leg in plan.legs] == [
        ("R1", ["A", "X"]),
        ("R2", ["X", "D"]),
    ]


def test_stays_on_the_same_bus_when_equally_fast() -> None:
    # R1 and R2 both run A-B at 2 min; only R1 continues to C.
    graph = _network({"R1": [("A", 2), ("B", 2), ("C", 0)], "R2": [("A", 2), ("B", 0)]})

    plan = plan_journey(graph, "A", "C")

    assert plan is not None
    assert [leg.route_id for leg in plan.legs] == ["R1"]


def test_unreachable_destination_has_no_plan() -> None:
    graph = _network({"R1": [("A", 1), ("B", 0)], "R2": [("C", 1), ("D", 0)]})

    assert plan_journey(graph, "A", "D") is None


def test_leg_times_add_up_for_every_sample_journey(sample: nx.DiGraph) -> None:
    for origin, destination in permutations(sorted(sample.nodes), 2):
        plan = plan_journey(sample, origin, destination)
        assert plan is not None
        assert sum(leg.travel_time_min for leg in plan.legs) == pytest.approx(
            plan.travel_time_min, abs=0.05 * len(plan.legs)
        )
        # Legs connect: each starts where the previous one ended.
        for previous, leg in pairwise(plan.legs):
            assert previous.stop_ids[-1] == leg.stop_ids[0]


# --- Closed stops -----------------------------------------------------------------------

def test_journey_drives_through_closed_stop(sample: nx.DiGraph) -> None:
    result = compare_journey(sample, _request("NTH", "STH", {"type": "close_stop", "stop_id": "CEN"}))

    assert result.status == "slower"
    assert result.after is not None
    (leg,) = result.after.legs
    assert leg.route_id == "R1"
    assert leg.stop_ids == ["NTH", "UNI", "MKT", "CEN", "HOS", "STH"]
    assert leg.passes_closed_stop_ids == ["CEN"]
    assert leg.travel_time_min == 19.0


def test_two_adjacent_closed_stops_are_both_listed() -> None:
    graph = _network({"R1": [("A", 1), ("B", 2), ("C", 3), ("D", 0)]})

    result = compare_journey(graph, _request(
        "A", "D",
        {"type": "close_stop", "stop_id": "B"},
        {"type": "close_stop", "stop_id": "C"},
    ))

    assert result.status == "unchanged"
    assert result.after is not None
    assert result.after.legs[0].stop_ids == ["A", "B", "C", "D"]
    assert result.after.legs[0].passes_closed_stop_ids == ["B", "C"]


@pytest.mark.parametrize(
    ("origin", "destination", "reason"),
    [
        ("CEN", "MKT", "origin stop is closed"),
        ("MKT", "CEN", "destination stop is closed"),
    ],
)
def test_closed_origin_or_destination_is_impossible_with_reason(
    sample: nx.DiGraph, origin: str, destination: str, reason: str
) -> None:
    result = compare_journey(sample, _request(origin, destination, {"type": "close_stop", "stop_id": "CEN"}))

    assert (result.status, result.after, result.change_min) == ("impossible", None, None)
    assert result.reason is not None and reason in result.reason
    assert result.before is not None


def test_cut_off_destination_is_impossible_with_reason(sample: nx.DiGraph) -> None:
    result = compare_journey(sample, _request(
        "NTH", "AIR", {"type": "remove_connection", "from_stop_id": "TEC", "to_stop_id": "AIR"}))

    assert result.status == "impossible"
    assert result.reason == "No connection remains between these stops after the changes."


def test_never_connected_stops_are_unreachable() -> None:
    graph = _network({"R1": [("A", 1), ("B", 0)], "R2": [("C", 1), ("D", 0)]})

    result = compare_journey(graph, _request("A", "D"))

    assert (result.status, result.before, result.after) == ("unreachable", None, None)


# --- Agreement with the simulation ---------------------------------------------------------

@pytest.mark.parametrize(
    "changes",
    [
        [{"type": "close_stop", "stop_id": "CEN"}],
        [{"type": "remove_connection", "from_stop_id": "TEC", "to_stop_id": "AIR"}],
        [{"type": "change_travel_time", "from_stop_id": "RIV", "to_stop_id": "EST",
          "travel_time_min": 7.5, "both_directions": False}],
    ],
)
def test_explorer_agrees_with_simulation_for_every_journey(
    sample: nx.DiGraph, changes: list[dict[str, Any]]
) -> None:
    simulation = simulate(sample, Scenario.model_validate({"changes": changes}))
    changed = {(j.origin_id, j.destination_id): j for j in simulation.changed_journeys}
    _, closed = apply_scenario(sample, Scenario.model_validate({"changes": changes}))

    for origin, destination in permutations(sorted(sample.nodes), 2):
        if origin in closed or destination in closed:
            continue
        result = compare_journey(sample, _request(origin, destination, *changes))
        expected = changed.get((origin, destination))
        if expected is None:
            assert result.status == "unchanged", (origin, destination)
        else:
            assert result.status == expected.status, (origin, destination)
            assert result.change_min == expected.change_min, (origin, destination)


# --- Validation and safety -----------------------------------------------------------------

def test_unknown_stop_raises(sample: nx.DiGraph) -> None:
    with pytest.raises(JourneyError, match="Unknown stop 'XXX'"):
        compare_journey(sample, _request("XXX", "CEN"))


def test_invalid_change_raises_scenario_error(sample: nx.DiGraph) -> None:
    with pytest.raises(ScenarioError, match="Change 1"):
        compare_journey(sample, _request("NTH", "STH", {"type": "close_stop", "stop_id": "NOPE"}))


def test_same_origin_and_destination_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be different"):
        _request("CEN", "CEN")


def test_baseline_is_never_modified(sample: nx.DiGraph) -> None:
    snapshot = copy.deepcopy(sample)

    compare_journey(sample, _request("NTH", "STH", {"type": "close_stop", "stop_id": "CEN"}))

    assert list(sample.edges(data=True)) == list(snapshot.edges(data=True))
    assert not any("route_via" in data for *_, data in sample.edges(data=True))
