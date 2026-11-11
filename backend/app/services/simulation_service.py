"""Apply a scenario to a copy of the baseline graph and measure the impact.

Rules (CLAUDE.md, docs/IMPLEMENTATION_PLAN.md):
- The baseline graph is never modified; all changes go to a deep copy.
- Every number is computed deterministically from the two graphs.

Passenger journeys = every ordered pair of distinct stops, weighted equally
(there is no demand data, and inventing passenger numbers would be fake data).
A journey's time is the fastest path; there is no transfer penalty.

Closing a stop (option B): nobody can board, alight or transfer there, but
buses still drive through. For every route that ran  P -> S -> N  a bypass
edge  P -> N  is added with that route's own times (P->S + S->N).
This assumes each route is a simple line or loop (no branches), which holds
for the sample network.
"""

import copy
from collections.abc import Sequence

import networkx as nx

from app.schemas.scenario import ChangeTravelTime, CloseStop, RemoveConnection, Scenario
from app.schemas.simulation import (
    JourneyChange,
    SimulationResult,
    SimulationSummary,
    StopImpact,
)
from app.services.network_service import add_route_edge

# Two travel times closer than this are equal (guards against float noise,
# e.g. (a + b) + c vs a + (b + c) when a bypass edge replaces two edges).
_EPSILON = 1e-9
_MOST_AFFECTED_LIMIT = 5


class ScenarioError(ValueError):
    """The scenario cannot be applied to the network (e.g. unknown stop)."""


# --- Applying changes -------------------------------------------------------

def apply_scenario(
    baseline: nx.DiGraph, scenario: Scenario
) -> tuple[nx.DiGraph, set[str]]:
    """Return (modified copy of the baseline, ids of closed stops)."""
    graph = copy.deepcopy(baseline)
    closed: set[str] = set()

    for number, change in enumerate(scenario.changes, start=1):
        try:
            if isinstance(change, CloseStop):
                _close_stop(graph, change.stop_id, closed)
            elif isinstance(change, RemoveConnection):
                for u, v in _target_edges(graph, change, closed):
                    graph.remove_edge(u, v)
            elif isinstance(change, ChangeTravelTime):
                for u, v in _target_edges(graph, change, closed):
                    _set_travel_time(graph, u, v, change.travel_time_min)
            else:  # pragma: no cover - guarded by the Pydantic discriminator
                raise ScenarioError(f"Unsupported change type: {change!r}")
        except ScenarioError as error:
            raise ScenarioError(f"Change {number} ({change.type}): {error}") from None
    return graph, closed


def _require_open_stop(graph: nx.DiGraph, stop_id: str, closed: set[str]) -> None:
    if stop_id in closed:
        raise ScenarioError(f"stop '{stop_id}' is already closed by an earlier change")
    if stop_id not in graph:
        raise ScenarioError(f"unknown stop '{stop_id}'")


def _close_stop(graph: nx.DiGraph, stop_id: str, closed: set[str]) -> None:
    _require_open_stop(graph, stop_id, closed)

    bypasses: list[tuple[str, str, str, float]] = []
    for pred in graph.predecessors(stop_id):
        times_in: dict[str, float] = graph.edges[pred, stop_id]["route_times"]
        for succ in graph.successors(stop_id):
            if succ == pred:  # turning back is not a through movement
                continue
            times_out: dict[str, float] = graph.edges[stop_id, succ]["route_times"]
            for route_id in times_in.keys() & times_out.keys():
                bypasses.append(
                    (pred, succ, route_id, times_in[route_id] + times_out[route_id])
                )

    graph.remove_node(stop_id)
    for pred, succ, route_id, minutes in sorted(bypasses):  # sorted: deterministic
        add_route_edge(graph, pred, succ, route_id, minutes)
    closed.add(stop_id)


def _target_edges(
    graph: nx.DiGraph,
    change: RemoveConnection | ChangeTravelTime,
    closed: set[str],
) -> list[tuple[str, str]]:
    """Edges a link change applies to; all are validated before any is changed."""
    a, b = change.from_stop_id, change.to_stop_id
    _require_open_stop(graph, a, closed)
    _require_open_stop(graph, b, closed)

    edges = [(a, b), (b, a)] if change.both_directions else [(a, b)]
    for u, v in edges:
        if not graph.has_edge(u, v):
            raise ScenarioError(f"no connection from '{u}' to '{v}'")
    return edges


def _set_travel_time(graph: nx.DiGraph, u: str, v: str, minutes: float) -> None:
    edge = graph.edges[u, v]
    graph.add_edge(
        u,
        v,
        route_times={route_id: minutes for route_id in edge["route_times"]},
        routes=list(edge["routes"]),
        weight=minutes,
    )


# --- Metrics ----------------------------------------------------------------

def simulate(baseline: nx.DiGraph, scenario: Scenario) -> SimulationResult:
    """Apply the scenario to a copy of the baseline and compare journeys."""
    modified, closed = apply_scenario(baseline, scenario)

    before = dict(nx.all_pairs_dijkstra_path_length(baseline, weight="weight"))
    after = dict(nx.all_pairs_dijkstra_path_length(modified, weight="weight"))
    stop_ids = sorted(baseline.nodes)

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
            time_after = after.get(origin, {}).get(destination)
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
