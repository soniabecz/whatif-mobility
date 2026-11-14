"""Walking (Day 10 part 3; Day 14 part 3: walking between stops).

Passengers walk (straight line x 1.3) at the start (<= max_walk_m), between
two buses (<= max_transfer_walk_m, a change of bus) and at the end, or the
whole way; never twice in a row. ``between_open_stops=False`` is the Day 10
rule: walking only from or to a CLOSED stop. Walking off reproduces the
earlier engine (the other test files mostly run with walking off).
"""

import copy
from itertools import permutations
from typing import Any

import networkx as nx
import numpy as np
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
from app.services.simulation_service import simulate
from app.services.route_graph import build_route_graph, travel_time_matrix
from app.services.walking import (
    WALK_DETOUR,
    WalkingModel,
    add_walking_layer,
    journey_time_matrix,
    straight_line_m,
    walks_within,
)

METRES_PER_DEGREE_LAT = 6_371_000 * 3.141592653589793 / 180  # ~111,195 m

# 6 km/h = 100 m per minute, so minutes = walking metres / 100.
WALK = WalkingModel(speed_kmh=6, max_walk_m=1000)
CLOSED_ONLY = WalkingModel(speed_kmh=6, max_walk_m=1000, between_open_stops=False)


def _line_north(spacing_m: float, minutes: float, stop_ids: list[str]) -> nx.DiGraph:
    """Stops due north of each other, `spacing_m` apart, on one two-way route."""
    stops = [
        Stop(id=s, name=s, lat=i * spacing_m / METRES_PER_DEGREE_LAT, lon=0.0, activity=1)
        for i, s in enumerate(stop_ids)
    ]
    connections = []
    for a, b in zip(stop_ids, stop_ids[1:], strict=False):
        connections += [
            Connection(route_id="R1", from_stop_id=a, to_stop_id=b, travel_time_min=minutes),
            Connection(route_id="R1", from_stop_id=b, to_stop_id=a, travel_time_min=minutes),
        ]
    routes = [Route(id="R1", name="R1", color="#000000", headway_min=10)]
    return build_graph(stops, connections, routes)


# P -500 m- Q -500 m- R, bus 5 min per stretch. Walking 500 m straight = 650 m = 6.5 min;
# 1000 m straight = 1300 m walking: out of reach.
LINE = _line_north(500, 5, ["P", "Q", "R"])
CLOSE_P = Scenario.model_validate({"changes": [{"type": "close_stop", "stop_id": "P"}]})


def _times(result: Any) -> dict[tuple[str, str], tuple[float, float | None, str]]:
    return {(j.origin_id, j.destination_id): (j.time_before_min, j.time_after_min, j.status)
            for j in result.changed_journeys}


def test_distance_is_straight_line_times_detour() -> None:
    assert straight_line_m(0, 0, 500 / METRES_PER_DEGREE_LAT, 0) == pytest.approx(500, abs=0.01)
    walks = [w for w in walks_within(LINE, ["P", "Q", "R"], WALK) if w.from_stop_id == "P"]
    assert [(w.to_stop_id, round(w.distance_m, 1), round(w.minutes, 2)) for w in walks] == [
        ("Q", 500 * WALK_DETOUR, 6.5)  # R is 1300 m away: out of reach
    ]


def test_nobody_boards_at_a_closed_stop_reached_on_foot() -> None:
    both = Scenario.model_validate({"changes": [
        {"type": "close_stop", "stop_id": "P"}, {"type": "close_stop", "stop_id": "Q"},
    ]})
    times = _times(simulate(LINE, both, walking=WALK))
    assert times[("P", "R")] == (10.0, None, "impossible")  # Q is near but closed; R too far
    assert times[("P", "Q")] == (5.0, 6.5, "slower")  # walking the whole way still works


def test_closed_origin_walks_to_the_next_stop_and_takes_the_bus() -> None:
    times = _times(simulate(LINE, CLOSE_P, walking=WALK))
    assert times[("P", "R")] == (10.0, 11.5, "slower")  # walk 6.5 to Q + bus 5
    assert times[("R", "P")] == (10.0, 11.5, "slower")  # bus 5 to Q + walk 6.5


def test_a_walk_all_the_way_when_the_other_stop_is_near() -> None:
    assert _times(simulate(LINE, CLOSE_P, walking=WALK))[("P", "Q")] == (5.0, 6.5, "slower")


def test_no_stop_within_reach_means_impossible() -> None:
    short = WalkingModel(speed_kmh=6, max_walk_m=600)  # 650 m is too far
    result = simulate(LINE, CLOSE_P, walking=short)
    assert _times(result)[("P", "R")] == (10.0, None, "impossible")
    assert result.summary.impossible == 4  # P <-> Q and P <-> R


def test_summary_counts_walked_journeys_and_keeps_the_totals() -> None:
    walked = simulate(LINE, CLOSE_P, walking=WALK).summary
    excluded = simulate(LINE, CLOSE_P).summary
    assert (walked.walked_to_or_from_closed_stop, walked.to_or_from_closed_stop) == (4, 0)
    assert (excluded.walked_to_or_from_closed_stop, excluded.to_or_from_closed_stop) == (0, 4)
    for s in (walked, excluded):
        parts = s.unchanged + s.slower + s.faster + s.impossible + s.to_or_from_closed_stop
        assert parts == s.total_journeys


def test_explorer_shows_the_walking_legs() -> None:
    request = JourneyRequest(origin_id="P", destination_id="R", changes=CLOSE_P.changes)
    comparison = compare_journey(LINE, request, walking=WALK)
    after = comparison.after
    assert after is not None and len(after.walks) == 1
    walk = after.walks[0]
    assert (walk.from_stop_id, walk.to_stop_id, walk.before_leg) == ("P", "Q", 0)
    assert (walk.distance_m, walk.minutes) == (650, 6.5)
    assert [leg.route_id for leg in after.legs] == ["R1"]
    assert (after.travel_time_min, after.walk_min, after.in_vehicle_min) == (11.5, 6.5, 5.0)
    assert (comparison.status, comparison.change_min) == ("slower", 1.5)


def test_explorer_walk_only_and_unreachable() -> None:
    walk_only = compare_journey(
        LINE, JourneyRequest(origin_id="P", destination_id="Q", changes=CLOSE_P.changes), walking=WALK
    )
    assert walk_only.after is not None
    assert (walk_only.after.legs, walk_only.after.walk_min) == ([], 6.5)

    too_far = compare_journey(
        LINE,
        JourneyRequest(origin_id="P", destination_id="R", changes=CLOSE_P.changes),
        walking=WalkingModel(speed_kmh=6, max_walk_m=600),
    )
    assert too_far.status == "impossible"
    assert too_far.reason is not None and "within 600 m" in too_far.reason


def test_closed_stops_only_never_affects_journeys_between_open_stops() -> None:
    scenario = Scenario.model_validate(
        {"changes": [{"type": "remove_connection", "from_stop_id": "Q", "to_stop_id": "R"}]}
    )
    with_walking = simulate(LINE, scenario, walking=CLOSED_ONLY)
    assert with_walking.model_copy(update={"summary": with_walking.summary.model_copy(
        update={"walking": None})}) == simulate(LINE, scenario)


# --- Walking between open stops (Day 14 part 3) ------------------------------------------

def _network(stops: dict[str, float], routes: dict[str, list[tuple[str, str, float]]]) -> nx.DiGraph:
    """Stops at the given metres due north; each route runs its (from, to, minutes)
    stretches in both directions, a bus every 10 min."""
    stop_rows = [Stop(id=s, name=s, lat=m / METRES_PER_DEGREE_LAT, lon=0.0, activity=1) for s, m in stops.items()]
    connections = [
        Connection(route_id=route_id, from_stop_id=u, to_stop_id=v, travel_time_min=minutes)
        for route_id, stretches in routes.items()
        for a, b, minutes in stretches
        for u, v in ((a, b), (b, a))
    ]
    route_rows = [Route(id=r, name=r, color="#000000", headway_min=10) for r in routes]
    return build_graph(stop_rows, connections, route_rows)


def test_walking_beats_a_slow_bus_between_open_stops() -> None:
    # A and B are 400 m apart (520 m on foot = 5.2 min); the bus takes 30 min.
    network = _network({"A": 0, "B": 400}, {"R1": [("A", "B", 30)]})
    plan = plan_journey(network, "A", "B", walking=WALK)
    assert plan is not None and (plan.travel_time_min, plan.legs, plan.walk_min) == (5.2, [], 5.2)
    assert plan_journey(network, "A", "B", walking=CLOSED_ONLY).travel_time_min == 30.0  # type: ignore[union-attr]


def test_walking_between_two_buses_is_a_change_of_bus() -> None:
    # R1 A-B, R2 C-D; B and C 300 m apart (390 m on foot = 3.9 min).
    network = _network(
        {"A": 0, "B": 2000, "C": 2300, "D": 4300}, {"R1": [("A", "B", 5)], "R2": [("C", "D", 5)]}
    )
    plan = plan_journey(network, "A", "D", transfer_penalty_min=2, walking=WALK)
    assert plan is not None
    assert [(leg.route_id, leg.stop_ids) for leg in plan.legs] == [("R1", ["A", "B"]), ("R2", ["C", "D"])]
    assert [(w.from_stop_id, w.to_stop_id, w.minutes, w.before_leg) for w in plan.walks] == [("B", "C", 3.9, 1)]
    assert (plan.travel_time_min, plan.transfers) == (15.9, 1)  # 5 + 3.9 + 2 + 5


def test_walks_between_buses_are_limited_to_the_transfer_maximum() -> None:
    # B and C 450 m apart = 585 m on foot: more than 500 m between buses.
    network = _network(
        {"A": 0, "B": 2000, "C": 2450, "D": 4450}, {"R1": [("A", "B", 5)], "R2": [("C", "D", 5)]}
    )
    assert plan_journey(network, "A", "D", walking=WALK) is None
    longer = WalkingModel(speed_kmh=6, max_walk_m=1000, max_transfer_walk_m=600)
    assert plan_journey(network, "A", "D", walking=longer) is not None


def test_never_two_walks_in_a_row() -> None:
    # X, Y, Z 700 m apart (910 m on foot each; X-Z 1,820 m is too far), bus 30 min a stretch.
    network = _network({"X": 0, "Y": 700, "Z": 1400}, {"R1": [("X", "Y", 30), ("Y", "Z", 30)]})
    plan = plan_journey(network, "X", "Z", walking=WALK)
    assert plan is not None and plan.travel_time_min == 39.1  # walk 9.1 + bus 30, not 18.2 on foot
    assert len(plan.walks) == 1 and len(plan.legs) == 1


def test_baseline_and_scenario_walk_alike() -> None:
    # Removing the slow bus changes nothing: walking was already faster before.
    network = _network({"A": 0, "B": 400}, {"R1": [("A", "B", 30)]})
    scenario = Scenario.model_validate({"changes": [{"type": "remove_connection", "from_stop_id": "A", "to_stop_id": "B"}]})
    summary = simulate(network, scenario, walking=WALK).summary
    assert (summary.unchanged, summary.slower, summary.average_time_before_min) == (2, 0, 5.2)


# --- Sample network ------------------------------------------------------------------------

@pytest.fixture
def sample(db: Session) -> nx.DiGraph:
    return build_graph_from_db(db)


SAMPLE_WALK = WalkingModel(speed_kmh=5, max_walk_m=1000)


@pytest.mark.parametrize(
    "changes",
    [
        [{"type": "close_stop", "stop_id": "CEN"}],
        [{"type": "close_stop", "stop_id": "AIR"}],  # no stop within reach
        [{"type": "close_stop", "stop_id": "MKT"}, {"type": "close_stop", "stop_id": "UNI"}],
    ],
)
def test_explorer_agrees_with_simulation_with_walking(
    sample: nx.DiGraph, changes: list[dict[str, Any]]
) -> None:
    scenario = Scenario.model_validate({"changes": changes})
    simulation = simulate(sample, scenario, 2.0, True, SAMPLE_WALK)
    changed = {(j.origin_id, j.destination_id): j for j in simulation.changed_journeys}

    for origin, destination in permutations(sorted(sample.nodes), 2):
        request = JourneyRequest(origin_id=origin, destination_id=destination, changes=changes)
        result = compare_journey(sample, request, 2.0, True, SAMPLE_WALK)
        expected = changed.get((origin, destination))
        if expected is None:
            assert result.status == "unchanged", (origin, destination)
            continue
        assert (result.status, result.change_min) == (expected.status, expected.change_min)
        if result.after is not None:
            a = result.after
            parts = a.walk_min + a.in_vehicle_min + a.wait_min + a.transfers * a.transfer_penalty_min
            assert a.travel_time_min == pytest.approx(parts, abs=0.2), (origin, destination)


def test_closing_the_airport_makes_its_journeys_impossible(sample: nx.DiGraph) -> None:
    # Tech Park, its nearest stop, is about 1,200 m walking away (> 1,000 m).
    scenario = Scenario.model_validate({"changes": [{"type": "close_stop", "stop_id": "AIR"}]})
    summary = simulate(sample, scenario, 2.0, True, SAMPLE_WALK).summary
    assert (summary.impossible, summary.walked_to_or_from_closed_stop) == (30, 30)


def test_baseline_is_never_modified(sample: nx.DiGraph) -> None:
    snapshot = copy.deepcopy(sample)
    scenario = Scenario.model_validate({"changes": [{"type": "close_stop", "stop_id": "CEN"}]})
    simulate(sample, scenario, 2.0, True, SAMPLE_WALK)
    compare_journey(
        sample, JourneyRequest(origin_id="CEN", destination_id="AIR", changes=scenario.changes),
        2.0, True, SAMPLE_WALK,
    )
    assert nx.utils.graphs_equal(sample, snapshot)
    assert dict(sample.nodes(data=True)) == dict(snapshot.nodes(data=True))


def test_no_two_walks_in_a_row_by_boarding_and_getting_off_at_once(sample: nx.DiGraph) -> None:
    # CEN and UNI closed: walking CEN -> LIB, boarding and leaving the bus at LIB at
    # once, then walking LIB -> UNI would be 25.8 min. A walk after a bus needs a
    # real ride: walk to LIB, R3 to OLD, walk to UNI.
    # (Day 10 rule, as checked against the engine before step A.)
    model = WalkingModel(5, 1000, between_open_stops=False)
    changes = [{"type": "close_stop", "stop_id": "CEN"}, {"type": "close_stop", "stop_id": "UNI"}]
    simulation = simulate(sample, Scenario.model_validate({"changes": changes}), 2.0, True, model)
    assert _times(simulation)[("CEN", "UNI")] == (11.0, 30.5, "slower")
    after = compare_journey(
        sample, JourneyRequest(origin_id="CEN", destination_id="UNI", changes=changes), 2.0, True, model,
    ).after
    assert after is not None
    assert [(leg.route_id, leg.stop_ids) for leg in after.legs] == [("R3", ["LIB", "OLD"])]
    assert [(w.from_stop_id, w.to_stop_id, w.before_leg) for w in after.walks] == [
        ("CEN", "LIB", 0), ("OLD", "UNI", 1)]


def test_walking_the_whole_way_has_no_transfer_penalty() -> None:
    # The penalty is subtracted once for the first boarding; a walk has none.
    result = simulate(LINE, CLOSE_P, transfer_penalty_min=5, walking=WALK)
    assert _times(result)[("P", "Q")] == (5.0, 6.5, "slower")
    plan = compare_journey(
        LINE, JourneyRequest(origin_id="P", destination_id="Q", changes=CLOSE_P.changes), 5, walking=WALK,
    ).after
    assert plan is not None and (plan.travel_time_min, plan.transfers, plan.legs) == (6.5, 0, [])


def test_journey_matrix_without_walking_equals_the_route_graph_matrix(sample: nx.DiGraph) -> None:
    stops = sorted(sample.nodes)
    plain = build_route_graph(sample, 2.0, True)
    expected = travel_time_matrix(plain, stops)
    for model in (None, WalkingModel(5, 1000, between_open_stops=False)):  # none between open stops
        layered = build_route_graph(sample, 2.0, True)
        add_walking_layer(layered, sample, model, closed=())
        assert np.array_equal(journey_time_matrix(layered, stops).values, expected.values)  # exact


# --- Settings and API ----------------------------------------------------------------------

def test_walking_settings_defaults() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.walking == WalkingModel(speed_kmh=5, max_walk_m=1000)
    off = Settings(_env_file=None, walking_enabled=False)  # type: ignore[call-arg]
    assert off.walking is None


def test_api_uses_walking(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,  # type: ignore[call-arg]
        groq_api_key=None,
        transfer_penalty_min=2.0,
        include_waiting=True,
        walking_enabled=True,
    )
    changes = [{"type": "close_stop", "stop_id": "CEN"}]
    simulation = client.post("/api/simulations", json={"changes": changes})
    journey = client.post(
        "/api/journeys", json={"origin_id": "CEN", "destination_id": "AIR", "changes": changes}
    )
    assert simulation.status_code == journey.status_code == 200
    summary = simulation.json()["summary"]
    assert (summary["walked_to_or_from_closed_stop"], summary["to_or_from_closed_stop"]) == (30, 0)
    walk_start = journey.json()["after"]["walks"][0]
    assert walk_start["from_stop_id"] == "CEN" and walk_start["distance_m"] > 800
    assert summary["walking"] == {
        "speed_kmh": 5.0, "max_walk_m": 1000.0, "max_transfer_walk_m": 500.0, "between_open_stops": True,
    }


def test_a_walk_between_buses_is_never_longer_than_one_at_the_end() -> None:
    # Day 14 part 5: the smaller walking graph relies on it (see walking.py).
    with pytest.raises(ValueError, match="cannot be longer"):
        WalkingModel(speed_kmh=5, max_walk_m=400, max_transfer_walk_m=500)
    with pytest.raises(ValueError, match="MAX_TRANSFER_WALK_M"):
        Settings(_env_file=None, max_walk_m=400, max_transfer_walk_m=500)  # type: ignore[call-arg]
    assert WalkingModel(speed_kmh=5, max_walk_m=500, max_transfer_walk_m=500).max_transfer_walk_m == 500
