"""Walking to or from a closed stop (Day 10, part 3).

Only journeys touching a CLOSED stop walk: to a nearby open stop (straight
line x 1.3, within the maximum), then by bus; or the whole way. Walking off
reproduces the earlier engine (checked in full against it; the other test
files run with walking off).
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
from app.services.journey_service import compare_journey
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
    assert after is not None and after.walk_start is not None
    assert (after.walk_start.from_stop_id, after.walk_start.to_stop_id) == ("P", "Q")
    assert (after.walk_start.distance_m, after.walk_start.minutes) == (650, 6.5)
    assert after.walk_end is None
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


def test_walking_never_affects_journeys_between_open_stops() -> None:
    scenario = Scenario.model_validate(
        {"changes": [{"type": "remove_connection", "from_stop_id": "Q", "to_stop_id": "R"}]}
    )
    assert simulate(LINE, scenario, walking=WALK) == simulate(LINE, scenario)


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
    changes = [{"type": "close_stop", "stop_id": "CEN"}, {"type": "close_stop", "stop_id": "UNI"}]
    simulation = simulate(sample, Scenario.model_validate({"changes": changes}), 2.0, True, SAMPLE_WALK)
    assert _times(simulation)[("CEN", "UNI")] == (11.0, 30.5, "slower")
    after = compare_journey(
        sample, JourneyRequest(origin_id="CEN", destination_id="UNI", changes=changes), 2.0, True, SAMPLE_WALK,
    ).after
    assert after is not None and after.walk_start is not None and after.walk_end is not None
    assert [(leg.route_id, leg.stop_ids) for leg in after.legs] == [("R3", ["LIB", "OLD"])]
    assert (after.walk_start.to_stop_id, after.walk_end.from_stop_id) == ("LIB", "OLD")


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
    for model in (None, SAMPLE_WALK):  # Day 10 walking: none between open stops
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
    walk_start = journey.json()["after"]["walk_start"]
    assert walk_start["from_stop_id"] == "CEN" and walk_start["distance_m"] > 800
