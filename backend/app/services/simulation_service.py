"""Apply a scenario to a copy of the baseline network and measure the impact.

Rules (CLAUDE.md, docs/IMPLEMENTATION_PLAN.md):
- The baseline is never modified; changes go to a newly built route graph.
- Every number is computed deterministically from the two graphs.

Passenger journeys = every ordered pair of distinct stops, weighted equally
(there is no demand data, and inventing passenger numbers would be fake data).
Next to these, ``demand_weighted`` repeats the figures with each journey
weighted by origin activity x destination activity (INVENTED stop levels 1-3),
reported only as shares and averages. Equal levels give the unweighted figures.
A journey's time is the fastest path in the route-aware graph
(see route_graph.py): time on the bus, plus (optionally) waiting half the
headway at every boarding, plus a fixed penalty per change of bus.

Closing a stop: nobody can board, alight or change bus there, but buses still
drive through it (its platforms and ride edges stay in the route graph).
Journeys to or from a closed stop are excluded from the figures, unless a
``WalkingModel`` is given: then passengers walk to a nearby open stop (see
walking.py) and those journeys are compared like any other.
"""

from collections.abc import Sequence

import networkx as nx

from app.schemas.scenario import (
    AddConnection,
    AddRoute,
    AddStop,
    ChangeFrequency,
    ChangeTravelTime,
    CloseStop,
    RemoveConnection,
    Scenario,
)
from app.schemas.simulation import (
    DemandWeighted,
    NewStops,
    JourneyChange,
    SimulationResult,
    SimulationSummary,
    StopImpact,
)
from app.services.route_graph import (
    Platform,
    add_ride,
    add_route,
    added_stop_ids,
    build_route_graph,
    is_open_stop,
    ride_edges,
    route_ids,
    set_headway,
    travel_times_from,
)
from app.services.walking import WalkingModel, best_walk_option

# Two travel times closer than this are equal (guards against float noise).
_EPSILON = 1e-9
_MOST_AFFECTED_LIMIT = 5


class ScenarioError(ValueError):
    """The scenario cannot be applied to the network (e.g. unknown stop)."""


# --- Applying changes -------------------------------------------------------

def apply_scenario(
    baseline: nx.DiGraph,
    scenario: Scenario,
    transfer_penalty_min: float = 0.0,
    include_waiting: bool = False,
) -> tuple[nx.DiGraph, set[str]]:
    """Return (modified route graph built from the baseline, ids of closed stops).

    ``baseline`` is the stop-level network graph; it is only read.
    """
    graph = build_route_graph(baseline, transfer_penalty_min, include_waiting)
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
            elif isinstance(change, ChangeFrequency):
                if change.route_id not in route_ids(graph):
                    raise ScenarioError(f"unknown route '{change.route_id}'")
                set_headway(graph, change.route_id, change.headway_min)
            elif isinstance(change, AddConnection):
                for u, v in _new_rides(graph, change, closed):
                    add_ride(graph, u, v, change.route_id, change.travel_time_min)
            elif isinstance(change, AddStop):
                _insert_stop(graph, change, closed)
            elif isinstance(change, AddRoute):
                _add_route(graph, change, closed)
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


def _insert_stop(graph: nx.DiGraph, change: AddStop, closed: set[str]) -> None:
    """Insert a new stop into a route between two consecutive stops (validated first)."""
    new, a, b, route = change.stop_id, change.from_stop_id, change.to_stop_id, change.route_id
    if new in graph or new in closed:
        raise ScenarioError(f"stop id '{new}' is already used")
    name = change.name.strip()
    if any(isinstance(n, str) and d.get("name") == name for n, d in graph.nodes(data=True)):
        raise ScenarioError(f"a stop called '{name}' already exists")
    _require_open_stop(graph, a, closed)
    _require_open_stop(graph, b, closed)
    if route not in route_ids(graph):
        raise ScenarioError(f"unknown route '{route}'")
    # (u, v, minutes u -> new, minutes new -> v) for each direction the route runs.
    legs = [
        (u, v, t_u, t_v)
        for u, v, t_u, t_v in ((a, b, change.time_from_min, change.time_to_min),
                               (b, a, change.time_to_min, change.time_from_min))
        if graph.has_edge((u, route), (v, route))
    ]
    if not legs or legs[0][0] != a:
        raise ScenarioError(f"route '{route}' does not run directly from '{a}' to '{b}'")

    graph.add_node(
        new, kind="stop", name=name, lat=change.lat, lon=change.lon, activity=1, added=True
    )
    for u, v, t_u, t_v in legs:
        graph.remove_edge((u, route), (v, route))  # buses now stop at the new stop
        add_ride(graph, u, new, route, t_u)
        add_ride(graph, new, v, route, t_v)


def _add_route(graph: nx.DiGraph, change: AddRoute, closed: set[str]) -> None:
    """Add a new route through existing (or earlier added) open stops (validated first)."""
    route = change.route_id
    if route in route_ids(graph) or route in graph.graph["headways"]:
        raise ScenarioError(f"route id '{route}' is already used")
    name = change.name.strip()
    if name in graph.graph.get("route_names", {}).values():
        raise ScenarioError(f"a route called '{name}' already exists")
    for stop_id in change.stop_ids:
        _require_open_stop(graph, stop_id, closed)

    add_route(graph, route, name, change.headway_min)
    for u, v, minutes in change.stretches():
        add_ride(graph, u, v, route, minutes)
        if change.both_directions:
            add_ride(graph, v, u, route, minutes)


def _new_rides(
    graph: nx.DiGraph, change: AddConnection, closed: set[str]
) -> list[tuple[str, str]]:
    """(from, to) pairs an added connection creates; validated before any change."""
    a, b, route = change.from_stop_id, change.to_stop_id, change.route_id
    _require_open_stop(graph, a, closed)
    _require_open_stop(graph, b, closed)
    if route not in route_ids(graph):
        raise ScenarioError(f"unknown route '{route}'")
    if (a, route) not in graph and (b, route) not in graph:
        raise ScenarioError(
            f"route '{route}' stops at neither '{a}' nor '{b}': "
            "a new link must start or end at a stop on the route"
        )
    directions = [(a, b), (b, a)] if change.both_directions else [(a, b)]
    for u, v in directions:
        if graph.has_edge((u, route), (v, route)):
            raise ScenarioError(
                f"route '{route}' already runs from '{u}' to '{v}' "
                "(use change_travel_time to change its time)"
            )
    return directions


# --- Metrics ----------------------------------------------------------------

def simulate(
    baseline: nx.DiGraph,
    scenario: Scenario,
    transfer_penalty_min: float = 0.0,
    include_waiting: bool = False,
    walking: WalkingModel | None = None,
) -> SimulationResult:
    """Apply the scenario to a copy of the baseline and compare journeys.

    ``transfer_penalty_min``: minutes added per change of bus (0 = free).
    ``include_waiting``: wait half the headway at every boarding.
    ``walking``: walk to/from closed stops (None = such journeys are excluded).
    """
    before_graph = build_route_graph(baseline, transfer_penalty_min, include_waiting)
    after_graph, closed = apply_scenario(
        baseline, scenario, transfer_penalty_min, include_waiting
    )
    stop_ids = sorted(baseline.nodes)
    new_stop_ids = added_stop_ids(after_graph)
    places = stop_places(baseline, after_graph)

    before = {s: travel_times_from(before_graph, s) for s in stop_ids}
    after = {
        s: travel_times_from(after_graph, s)
        for s in [*stop_ids, *new_stop_ids] if s not in closed
    }

    changed: list[JourneyChange] = []
    unchanged = closed_count = walked_count = newly_possible = 0
    sum_before = sum_after = 0.0
    comparable = 0
    # Demand weights: invented activity level of origin x destination.
    activity = {s: baseline.nodes[s].get("activity", 1) for s in stop_ids}
    weight_of: dict[str, float] = {}  # category -> summed weight
    weighted_before = weighted_after = weighted_comparable = 0.0

    def add_weight(category: str, weight: float) -> None:
        weight_of[category] = weight_of.get(category, 0.0) + weight
    per_stop: dict[str, list[JourneyChange]] = {s: [] for s in stop_ids}

    for origin in stop_ids:
        for destination in stop_ids:
            if origin == destination:
                continue
            weight = float(activity[origin] * activity[destination])
            time_before = before[origin].get(destination)
            if origin in closed or destination in closed:
                if walking is None:
                    closed_count += 1
                    add_weight("closed", weight)
                    continue
                walked_count += 1
                option = best_walk_option(
                    places, walking, origin, destination, closed,
                    lambda a, b: after[a].get(b),
                )
                time_after = option.total_min if option else None
            else:
                time_after = after[origin].get(destination)
            if time_before is None:
                # Impossible already in the baseline. An added connection can
                # make it possible; there is no "before" time to compare with.
                if time_after is None:
                    unchanged += 1
                    add_weight("unchanged", weight)
                else:
                    newly_possible += 1
                    add_weight("newly_possible", weight)
                continue

            if time_after is not None:
                comparable += 1
                sum_before += time_before
                sum_after += time_after
                weighted_comparable += weight
                weighted_before += weight * time_before
                weighted_after += weight * time_after
                if abs(time_after - time_before) < _EPSILON:
                    unchanged += 1
                    add_weight("unchanged", weight)
                    continue

            journey = _journey_change(origin, destination, time_before, time_after)
            add_weight(journey.status, weight)
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
        newly_possible=newly_possible,
        to_or_from_closed_stop=closed_count,
        walked_to_or_from_closed_stop=walked_count,
        average_time_before_min=_round(sum_before / comparable) if comparable else None,
        average_time_after_min=_round(sum_after / comparable) if comparable else None,
        total_time_change_min=_round(sum_after - sum_before),
        largest_increase=_largest_increase(changed),
        transfer_penalty_min=transfer_penalty_min,
        include_waiting=include_waiting,
        demand_weighted=_demand_weighted(
            weight_of, weighted_comparable, weighted_before, weighted_after
        ),
        new_stops=_new_stops(new_stop_ids, stop_ids, closed, after),
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


def stop_places(baseline: nx.DiGraph, after_graph: nx.DiGraph) -> nx.DiGraph:
    """Every stop with its coordinates: the baseline's (closed ones included)
    plus stops added by the scenario. Used for walking distances."""
    places = nx.DiGraph()
    places.add_nodes_from(baseline.nodes(data=True))
    for stop_id in added_stop_ids(after_graph):
        places.add_node(stop_id, **after_graph.nodes[stop_id])
    return places


def _new_stops(
    new_stop_ids: list[str],
    stop_ids: list[str],
    closed: set[str],
    after: dict[str, dict[str, float]],
) -> NewStops | None:
    """Journeys between open stops that involve at least one added stop."""
    if not new_stop_ids:
        return None
    open_stops = [s for s in [*stop_ids, *new_stop_ids] if s not in closed]
    new = set(new_stop_ids)
    times = [
        after[o].get(d)
        for o in open_stops for d in open_stops
        if o != d and (o in new or d in new)
    ]
    possible = [t for t in times if t is not None]
    return NewStops(
        stop_ids=new_stop_ids,
        journeys=len(times),
        possible=len(possible),
        average_time_min=_round(sum(possible) / len(possible)) if possible else None,
    )


def _demand_weighted(
    weight_of: dict[str, float], comparable: float, before: float, after: float
) -> DemandWeighted:
    total = sum(weight_of.values())

    def pct(category: str) -> float:
        return _round(100 * weight_of.get(category, 0.0) / total) if total else 0.0

    return DemandWeighted(
        unchanged_pct=pct("unchanged"),
        slower_pct=pct("slower"),
        faster_pct=pct("faster"),
        impossible_pct=pct("impossible"),
        newly_possible_pct=pct("newly_possible"),
        to_or_from_closed_stop_pct=pct("closed"),
        average_time_before_min=_round(before / comparable) if comparable else None,
        average_time_after_min=_round(after / comparable) if comparable else None,
    )


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
