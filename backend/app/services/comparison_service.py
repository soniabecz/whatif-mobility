"""Compare two scenarios journey by journey (Day 13).

Both scenarios are simulated against the same baseline with the same rules
(scenario_state), so every number is deterministic. Journeys are the
baseline's ordered stop pairs; journeys to or from stops added by a scenario
exist in only one of them and are left out (they appear in each summary's
new_stops figures).
"""

import networkx as nx

from app.schemas.saved_scenario import ComparisonResult, JourneyDifference
from app.schemas.scenario import Scenario
from app.services.route_graph import build_route_graph, travel_times_from
from app.services.simulation_service import scenario_state, simulate
from app.services.walking import WalkingModel

_EPSILON = 1e-9
_LARGEST_LIMIT = 10


def _round(value: float) -> float:
    return round(value, 1) + 0.0


def compare(
    baseline: nx.DiGraph,
    a: Scenario,
    b: Scenario,
    transfer_penalty_min: float = 0.0,
    include_waiting: bool = False,
    walking: WalkingModel | None = None,
) -> ComparisonResult:
    """Raises ScenarioError if either scenario does not fit the network."""
    settings = (transfer_penalty_min, include_waiting, walking)
    summary_a = simulate(baseline, a, *settings).summary
    summary_b = simulate(baseline, b, *settings).summary
    state_a = scenario_state(baseline, a, *settings)
    state_b = scenario_state(baseline, b, *settings)
    base_graph = build_route_graph(baseline, transfer_penalty_min, include_waiting)

    stop_ids = sorted(baseline.nodes)
    counts = {"same": 0, "a_faster": 0, "b_faster": 0, "only_a": 0, "only_b": 0, "neither": 0}
    differences: list[JourneyDifference] = []
    compared = 0
    for origin in stop_ids:
        base_times = travel_times_from(base_graph, origin)
        for destination in stop_ids:
            if origin == destination:
                continue
            if state_a.excludes(origin, destination) or state_b.excludes(origin, destination):
                continue
            compared += 1
            time_a = state_a.journey_time(origin, destination)
            time_b = state_b.journey_time(origin, destination)
            if time_a is None and time_b is None:
                counts["neither"] += 1
                continue
            if time_a is not None and time_b is not None and abs(time_a - time_b) < _EPSILON:
                counts["same"] += 1
                continue
            if time_b is None:
                counts["only_a"] += 1
            elif time_a is None:
                counts["only_b"] += 1
            elif time_a < time_b:
                counts["a_faster"] += 1
            else:
                counts["b_faster"] += 1
            base = base_times.get(destination)
            differences.append(
                JourneyDifference(
                    origin_id=origin,
                    destination_id=destination,
                    time_baseline_min=None if base is None else _round(base),
                    time_a_min=None if time_a is None else _round(time_a),
                    time_b_min=None if time_b is None else _round(time_b),
                    difference_min=(
                        None if time_a is None or time_b is None else _round(time_a - time_b)
                    ),
                )
            )

    # Largest first: possible in only one scenario, then the biggest gap; ids break ties.
    differences.sort(
        key=lambda d: (
            d.difference_min is not None,
            -abs(d.difference_min or 0.0),
            d.origin_id,
            d.destination_id,
        )
    )
    return ComparisonResult(
        a=summary_a,
        b=summary_b,
        compared_journeys=compared,
        same=counts["same"],
        a_faster=counts["a_faster"],
        b_faster=counts["b_faster"],
        only_possible_in_a=counts["only_a"],
        only_possible_in_b=counts["only_b"],
        impossible_in_both=counts["neither"],
        largest_differences=differences[:_LARGEST_LIMIT],
    )
