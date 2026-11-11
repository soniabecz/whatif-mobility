"""Apply a scenario to a copy of the baseline network and measure the impact.

Rules (CLAUDE.md, docs/IMPLEMENTATION_PLAN.md):
- The baseline is never modified; changes go to a newly built route graph.
- Every number is computed deterministically from the two graphs.

Passenger journeys = every ordered pair of distinct stops, weighted equally
(there is no demand data, and inventing passenger numbers would be fake data).
A journey's time is the fastest path in the route-aware graph
(see route_graph.py): time on the bus plus a fixed penalty per change of bus.

Closing a stop: nobody can board, alight or change bus there, but buses still
drive through it (its platforms and ride edges stay in the route graph).
"""

from collections.abc import Sequence

import networkx as nx

from app.schemas.scenario import ChangeTravelTime, CloseStop, RemoveConnection, Scenario
from app.schemas.simulation import (
    JourneyChange,
    SimulationResult,
    SimulationSummary,
    StopImpact,
)
from app.services.route_graph import (
    Platform,
    build_route_graph,
    is_open_stop,
    ride_edges,
    travel_times_from,
)

# Two travel times closer than this are equal (guards against float noise).
_EPSILON = 1e-9
_MOST_AFFECTED_LIMIT = 5


class ScenarioError(ValueError):
    """The scenario cannot be applied to the network (e.g. unknown stop)."""


# --- Applying changes -------------------------------------------------------

def apply_scenario(
    baseline: nx.DiGraph, scenario: Scenario, transfer_penalty_min: float = 0.0
) -> tuple[nx.DiGraph, set[str]]:
    """Return (modified route graph built from the baseline, ids of closed stops).

    ``baseline`` is the stop-level network graph; it is only read.
    """
    graph = build_route_graph(baseline, transfer_penalty_min)
    closed: set[str] = set()

    for number, change in enumerate(scenario.changes, start=1):
        try:
            if isinstance(change, CloseStop):
                _require_open_stop(graph, change.stop_id, closed)
                graph.remove_node(change.stop_id)  # platforms stay: buses drive through
                closed.add(change.stop_id)
            elif isinstance(change, RemoveConnection):
                graph.remove_edges_from(_target_rides(graph, change, closed))
            elif isinstance(change, ChangeTravelTime):
                for ride in _target_rides(graph, change, closed):
                    graph.edges[ride]["weight"] = change.travel_time_min
            else:  # pragma: no cover - guarded by the Pydantic discriminator
                raise ScenarioError(f"Unsupported change type: {change!r}")
        except ScenarioError as error:
            raise ScenarioError(f"Change {number} ({change.type}): {error}") from None
    return graph, closed


def _require_open_stop(graph: nx.DiGraph, stop_id: str, closed: set[str]) -> None:
    if stop_id in closed:
        raise ScenarioError(f"stop '{stop_id}' is already closed by an earlier change")
    if not is_open_stop(graph, stop_id):
        raise ScenarioError(f"unknown stop '{stop_id}'")


def _target_rides(
    graph: nx.DiGraph,
    change: RemoveConnection | ChangeTravelTime,
    closed: set[str],
) -> list[tuple[Platform, Platform]]:
    """Ride edges (all routes) a link change applies to; validated before any change."""
    a, b = change.from_stop_id, change.to_stop_id
    _require_open_stop(graph, a, closed)
    _require_open_stop(graph, b, closed)

    directions = [(a, b), (b, a)] if change.both_directions else [(a, b)]
    rides: list[tuple[Platform, Platform]] = []
    for u, v in directions:
        found = ride_edges(graph, u, v)
        if not found:
            raise ScenarioError(f"no connection from '{u}' to '{v}'")
        rides.extend(found)
    return rides


# --- Metrics ----------------------------------------------------------------

def simulate(
    baseline: nx.DiGraph, scenario: Scenario, transfer_penalty_min: float = 0.0
) -> SimulationResult:
    """Apply the scenario to a copy of the baseline and compare journeys.

    ``transfer_penalty_min``: minutes added per change of bus (0 = free).
    """
    before_graph = build_route_graph(baseline, transfer_penalty_min)
    after_graph, closed = apply_scenario(baseline, scenario, transfer_penalty_min)
    stop_ids = sorted(baseline.nodes)

    before = {s: travel_times_from(before_graph, s) for s in stop_ids}
    after = {s: travel_times_from(after_graph, s) for s in stop_ids if s not in closed}

    changed: list[JourneyChange] = []
    unchanged = closed_count = 0
    sum_before = sum_after = 0.0
    comparable = 0
    per_stop: dict[str, list[JourneyChange]] = {s: [] for s in stop_ids}

    for origin in stop_ids:
        for destination in stop_ids:
            if origin == destination:
                continue
            if origin in closed or destination in closed:
                closed_count += 1
                continue

            time_before = before[origin].get(destination)
            time_after = after[origin].get(destination)
            if time_before is None:
                # Impossible already in the baseline; changes only remove or
                # re-time links, so it cannot become possible. Not a change.
                unchanged += 1
                continue

            if time_after is not None:
                comparable += 1
                sum_before += time_before
                sum_after += time_after
                if abs(time_after - time_before) < _EPSILON:
                    unchanged += 1
                    continue

            journey = _journey_change(origin, destination, time_before, time_after)
            changed.append(journey)
            per_stop[origin].append(journey)
            per_stop[destination].append(journey)

    stop_impacts = [_stop_impact(s, s in closed, per_stop[s]) for s in stop_ids]
    summary = SimulationSummary(
        total_journeys=len(stop_ids) * (len(stop_ids) - 1),
        unchanged=unchanged,
        slower=sum(j.status == "slower" for j in changed),
        faster=sum(j.status == "faster" for j in changed),
        impossible=sum(j.status == "impossible" for j in changed),
        to_or_from_closed_stop=closed_count,
        average_time_before_min=_round(sum_before / comparable) if comparable else None,
        average_time_after_min=_round(sum_after / comparable) if comparable else None,
        total_time_change_min=_round(sum_after - sum_before),
        largest_increase=_largest_increase(changed),
        transfer_penalty_min=transfer_penalty_min,
    )
    return SimulationResult(
        scenario=scenario,
        summary=summary,
        changed_journeys=changed,
        stop_impacts=stop_impacts,
        most_affected_stop_ids=_most_affected(stop_impacts),
    )


def _round(value: float) -> float:
    return round(value, 1) + 0.0  # "+ 0.0" turns -0.0 into 0.0


def _journey_change(
    origin: str, destination: str, time_before: float, time_after: float | None
) -> JourneyChange:
    if time_after is None:
        return JourneyChange(
            origin_id=origin,
            destination_id=destination,
            time_before_min=_round(time_before),
            time_after_min=None,
            change_min=None,
            status="impossible",
        )
    return JourneyChange(
        origin_id=origin,
        destination_id=destination,
        time_before_min=_round(time_before),
        time_after_min=_round(time_after),
        change_min=_round(time_after - time_before),
        status="slower" if time_after > time_before else "faster",
    )


def _largest_increase(changed: Sequence[JourneyChange]) -> JourneyChange | None:
    largest: JourneyChange | None = None
    for journey in changed:  # already in (origin, destination) order
        if journey.status != "slower" or journey.change_min is None:
            continue
        if largest is None or journey.change_min > (largest.change_min or 0.0):
            largest = journey
    return largest


def _stop_impact(stop_id: str, closed: bool, journeys: list[JourneyChange]) -> StopImpact:
    changes = [j.change_min for j in journeys if j.change_min is not None]
    return StopImpact(
        stop_id=stop_id,
        closed=closed,
        affected_journeys=len(journeys),
        impossible_journeys=sum(j.status == "impossible" for j in journeys),
        average_change_min=_round(sum(changes) / len(changes)) if changes else None,
    )


def _most_affected(impacts: Sequence[StopImpact]) -> list[str]:
    """Rank: most impossible journeys, then most affected, then largest
    average change (either direction), then stop id for stable ties."""
    ranked = sorted(
        (i for i in impacts if i.affected_journeys > 0),
        key=lambda i: (
            -i.impossible_journeys,
            -i.affected_journeys,
            -abs(i.average_change_min or 0.0),
            i.stop_id,
        ),
    )
    return [i.stop_id for i in ranked[:_MOST_AFFECTED_LIMIT]]
