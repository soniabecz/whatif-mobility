"""Compare two scenarios journey by journey (Day 13).

Both scenarios are simulated against the same baseline with the same rules
(scenario_state), so every number is deterministic. Journeys are the
baseline's ordered stop pairs; journeys to or from stops added by a scenario
exist in only one of them and are left out (they appear in each summary's
new_stops figures).
"""

import networkx as nx
import numpy as np

from app.schemas.saved_scenario import ComparisonResult, JourneyDifference
from app.schemas.scenario import Scenario
from app.services.simulation_service import (
    baseline_times,
    journey_matrix,
    scenario_state,
    simulate_state,
)
from app.services.walking import WalkingModel

_EPSILON = 1e-9
_LARGEST_LIMIT = 10


def _round(value: float) -> float:
    return round(value, 1) + 0.0


def _time(value: float) -> float | None:
    return None if value == np.inf else _round(float(value))


def compare(
    baseline: nx.DiGraph,
    a: Scenario,
    b: Scenario,
    transfer_penalty_min: float = 0.0,
    include_waiting: bool = False,
    walking: WalkingModel | None = None,
) -> ComparisonResult:
    """Raises ScenarioError if either scenario does not fit the network."""
    state_a = scenario_state(baseline, a, transfer_penalty_min, include_waiting, walking)
    state_b = scenario_state(baseline, b, transfer_penalty_min, include_waiting, walking)
    summary_a = simulate_state(baseline, a, state_a, transfer_penalty_min, include_waiting).summary
    summary_b = simulate_state(baseline, b, state_b, transfer_penalty_min, include_waiting).summary

    stop_ids = sorted(baseline.nodes)
    n = len(stop_ids)
    base = baseline_times(baseline, transfer_penalty_min, include_waiting).values
    times_a, excluded_a = journey_matrix(state_a, stop_ids)
    times_b, excluded_b = journey_matrix(state_b, stop_ids)

    included = ~np.eye(n, dtype=bool) & ~excluded_a & ~excluded_b
    has_a, has_b = np.isfinite(times_a) & included, np.isfinite(times_b) & included
    both = has_a & has_b
    same = both.copy()
    same[both] = np.abs(times_a[both] - times_b[both]) < _EPSILON
    a_faster = both & ~same & (times_a < np.where(both, times_b, np.inf))
    b_faster = both & ~same & ~a_faster
    only_a, only_b = has_a & ~has_b, has_b & ~has_a
    neither = included & ~has_a & ~has_b

    # Largest first: possible in only one scenario, then the biggest (rounded)
    # gap; ids break ties.
    candidates = []
    for i, j in zip(*np.nonzero(a_faster | b_faster | only_a | only_b)):
        gap = _round(float(times_a[i, j] - times_b[i, j])) if both[i, j] else None
        candidates.append((gap is not None, -abs(gap or 0.0), stop_ids[i], stop_ids[j], i, j, gap))
    candidates.sort(key=lambda c: c[:4])
    differences = [
        JourneyDifference(
            origin_id=origin,
            destination_id=destination,
            time_baseline_min=_time(base[i, j]),
            time_a_min=_time(times_a[i, j]),
            time_b_min=_time(times_b[i, j]),
            difference_min=gap,
        )
        for _, _, origin, destination, i, j, gap in candidates[:_LARGEST_LIMIT]
    ]
    return ComparisonResult(
        a=summary_a,
        b=summary_b,
        compared_journeys=int(included.sum()),
        same=int(same.sum()),
        a_faster=int(a_faster.sum()),
        b_faster=int(b_faster.sum()),
        only_possible_in_a=int(only_a.sum()),
        only_possible_in_b=int(only_b.sum()),
        impossible_in_both=int(neither.sum()),
        largest_differences=differences,
    )
