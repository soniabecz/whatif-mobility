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
``WalkingModel`` is given: then passengers walk (see walking.py, which adds
walking to the route graph) and those journeys are compared like any other.
"""

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass

import networkx as nx
import numpy as np

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
    WalkingSettings,
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
    TimeMatrix,
)
from app.services.walking import WalkingModel, add_walking_layer, journey_time_matrix

# Two travel times closer than this are equal (guards against float noise).
_EPSILON = 1e-9
_MOST_AFFECTED_LIMIT = 5
MAX_CHANGED_JOURNEYS = 1000  # returned with a result; the CSV has all of them
_CHART_JOURNEYS = 10  # the results chart: largest changes still possible


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


# --- Journey times after a scenario --------------------------------------------

@dataclass(frozen=True)
class ScenarioState:
    """The network after a scenario, with every journey's fastest time.

    Shared by the simulation and the comparison of two scenarios, so both use
    exactly the same rules (closed stops, walking, added stops).
    """

    graph: nx.DiGraph  # route graph with its walking layer
    closed: set[str]
    new_stop_ids: list[str]
    # Fastest times between all stops, baseline and added, closed ones included
    # (reached on foot; inf without walking).
    times: TimeMatrix
    walking: WalkingModel | None

    def excludes(self, origin: str, destination: str) -> bool:
        """True for a journey to or from a closed stop when walking is off."""
        return self.walking is None and (origin in self.closed or destination in self.closed)


def scenario_state(
    baseline: nx.DiGraph,
    scenario: Scenario,
    transfer_penalty_min: float = 0.0,
    include_waiting: bool = False,
    walking: WalkingModel | None = None,
) -> ScenarioState:
    """Apply the scenario to a copy of the baseline and compute journey times."""
    graph, closed = apply_scenario(baseline, scenario, transfer_penalty_min, include_waiting)
    new_stop_ids = added_stop_ids(graph)
    add_walking_layer(graph, stop_places(baseline, graph), walking, closed)
    return ScenarioState(
        graph=graph,
        closed=closed,
        new_stop_ids=new_stop_ids,
        times=journey_time_matrix(graph, [*sorted(baseline.nodes), *new_stop_ids]),
        walking=walking,
    )


def journey_matrix(state: ScenarioState, stop_ids: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    """(times, excluded) for every pair of ``stop_ids`` after the scenario.

    ``times[i, j]``: fastest time (inf = impossible), walking as the model
    allows. ``excluded[i, j]``: a journey to or from a closed stop with walking
    off (left out of the figures). The diagonal is unused.
    """
    n = len(stop_ids)
    rows = [state.times.index[s] for s in stop_ids]
    times = np.array(state.times.values[np.ix_(rows, rows)])
    if state.walking is not None:
        return times, np.zeros((n, n), dtype=bool)
    closed = np.array([s in state.closed for s in stop_ids], dtype=bool)
    touches_closed = closed[:, None] | closed[None, :]
    times[touches_closed] = np.inf
    return times, touches_closed


# Times on today's network, per network and settings: every simulation needs
# them, and they only change when the network does (e.g. after an import).
_BASELINE_CACHE: OrderedDict[tuple[object, ...], TimeMatrix] = OrderedDict()
_BASELINE_CACHE_SIZE = 4


def _network_key(
    baseline: nx.DiGraph, transfer_penalty_min: float, include_waiting: bool, walking: WalkingModel | None
) -> tuple[object, ...]:
    return (
        transfer_penalty_min,
        include_waiting,
        walking,
        tuple(sorted((s, d["lat"], d["lon"]) for s, d in baseline.nodes(data=True))),
        tuple(sorted(baseline.graph.get("headways", {}).items())),
        tuple(sorted(baseline.nodes)),
        tuple(sorted((u, v, tuple(sorted(d["route_times"].items()))) for u, v, d in baseline.edges(data=True))),
    )


def baseline_times(
    baseline: nx.DiGraph,
    transfer_penalty_min: float,
    include_waiting: bool,
    walking: WalkingModel | None = None,
) -> TimeMatrix:
    """Fastest times between all stops of today's network (cached).

    ``walking``: the same model as the scenario's, so both sides walk alike."""
    key = _network_key(baseline, transfer_penalty_min, include_waiting, walking)
    if key in _BASELINE_CACHE:
        _BASELINE_CACHE.move_to_end(key)
        return _BASELINE_CACHE[key]
    graph = build_route_graph(baseline, transfer_penalty_min, include_waiting)
    add_walking_layer(graph, baseline, walking, closed=())
    times = journey_time_matrix(graph, sorted(baseline.nodes))
    _BASELINE_CACHE[key] = times
    if len(_BASELINE_CACHE) > _BASELINE_CACHE_SIZE:
        _BASELINE_CACHE.popitem(last=False)
    return times


def _ordered_sum(values: np.ndarray) -> float:
    """Sum added one by one in the given order, exactly like a ``+=`` loop
    (np.sum and Python 3.12's sum() round differently)."""
    return float(np.add.accumulate(values)[-1]) if values.size else 0.0


# --- Metrics ----------------------------------------------------------------

def simulate(
    baseline: nx.DiGraph,
    scenario: Scenario,
    transfer_penalty_min: float = 0.0,
    include_waiting: bool = False,
    walking: WalkingModel | None = None,
    max_changed: int | None = MAX_CHANGED_JOURNEYS,
) -> SimulationResult:
    """Apply the scenario to a copy of the baseline and compare journeys.

    ``transfer_penalty_min``: minutes added per change of bus (0 = free).
    ``include_waiting``: wait half the headway at every boarding.
    ``walking``: how passengers walk (None = no walking; journeys to or from a
    closed stop are then excluded).
    """
    state = scenario_state(baseline, scenario, transfer_penalty_min, include_waiting, walking)
    return simulate_state(baseline, scenario, state, transfer_penalty_min, include_waiting, max_changed)


def simulate_state(
    baseline: nx.DiGraph,
    scenario: Scenario,
    state: ScenarioState,
    transfer_penalty_min: float,
    include_waiting: bool,
    max_changed: int | None = MAX_CHANGED_JOURNEYS,
) -> SimulationResult:
    """The simulation's figures for an already applied scenario.

    ``max_changed``: how many changed journeys to list (None = all); every
    figure is computed from all of them."""
    closed, new_stop_ids = state.closed, state.new_stop_ids
    stop_ids = sorted(baseline.nodes)
    n = len(stop_ids)
    before = baseline_times(baseline, transfer_penalty_min, include_waiting, state.walking).values
    after, excluded = journey_matrix(state, stop_ids)

    # Every ordered pair of distinct stops, in (origin, destination) order:
    # all figures below are computed over these flattened arrays, and every
    # sum adds the values in this order (as the per-journey loop it replaces).
    pairs = ~np.eye(n, dtype=bool)
    activity = np.array([baseline.nodes[s].get("activity", 1) for s in stop_ids], dtype=np.int64)
    weight = (activity[:, None] * activity[None, :]).astype(float)[pairs]
    t_before, t_after, excl = before[pairs], after[pairs], excluded[pairs]
    closed_mask = np.array([s in closed for s in stop_ids], dtype=bool)
    walked = (closed_mask[:, None] | closed_mask[None, :])[pairs] & ~excl
    had, has = np.isfinite(t_before), np.isfinite(t_after)
    included = ~excl
    comparable = included & had & has
    same = comparable.copy()
    same[comparable] = np.abs(t_after[comparable] - t_before[comparable]) < _EPSILON
    newly = included & ~had & has
    unchanged = (included & ~had & ~has) | same
    slower = comparable & ~same & (t_after > t_before)
    faster = comparable & ~same & ~(t_after > t_before)
    impossible = included & had & ~has

    # Demand weights per category, summed in loop order; the categories in the
    # order the loop first met them (their sum is the total weight).
    categories = {
        "closed": excl, "unchanged": unchanged, "newly_possible": newly,
        "slower": slower, "faster": faster, "impossible": impossible,
    }
    first_seen = {name: int(np.argmax(mask)) for name, mask in categories.items() if mask.any()}
    weight_of = {
        name: _ordered_sum(weight[categories[name]])
        for name in sorted(first_seen, key=first_seen.__getitem__)
    }

    origins, destinations = np.nonzero(pairs)
    changed: list[JourneyChange] = []
    per_stop: dict[str, list[JourneyChange]] = {s: [] for s in stop_ids}
    for k in np.flatnonzero(slower | faster | impossible):
        origin, destination = stop_ids[origins[k]], stop_ids[destinations[k]]
        journey = _journey_change(
            origin, destination, float(t_before[k]), float(t_after[k]) if has[k] else None
        )
        changed.append(journey)
        per_stop[origin].append(journey)
        per_stop[destination].append(journey)

    count = int(comparable.sum())
    sum_before = _ordered_sum(t_before[comparable])
    sum_after = _ordered_sum(t_after[comparable])
    weighted_comparable = _ordered_sum(weight[comparable])
    weighted_before = _ordered_sum(weight[comparable] * t_before[comparable])
    weighted_after = _ordered_sum(weight[comparable] * t_after[comparable])
    after_times = state.times
    stop_impacts = [_stop_impact(s, s in closed, per_stop[s]) for s in stop_ids]
    summary = SimulationSummary(
        total_journeys=n * (n - 1),
        unchanged=int(unchanged.sum()),
        slower=int(slower.sum()),
        faster=int(faster.sum()),
        impossible=int(impossible.sum()),
        newly_possible=int(newly.sum()),
        to_or_from_closed_stop=int(excl.sum()),
        walked_to_or_from_closed_stop=int(walked.sum()),
        average_time_before_min=_round(sum_before / count) if count else None,
        average_time_after_min=_round(sum_after / count) if count else None,
        total_time_change_min=_round(sum_after - sum_before),
        largest_increase=_largest_increase(changed),
        transfer_penalty_min=transfer_penalty_min,
        include_waiting=include_waiting,
        walking=_walking_settings(state.walking),
        demand_weighted=_demand_weighted(
            weight_of, weighted_comparable, weighted_before, weighted_after
        ),
        new_stops=_new_stops(new_stop_ids, stop_ids, closed, after_times),
    )
    return SimulationResult(
        scenario=scenario,
        summary=summary,
        changed_journeys=_largest_changes(changed, max_changed),
        changed_journeys_total=len(changed),
        stop_impacts=stop_impacts,
        most_affected_stop_ids=_most_affected(stop_impacts),
    )


def _round(value: float) -> float:
    return round(value, 1) + 0.0  # "+ 0.0" turns -0.0 into 0.0


def _walking_settings(model: WalkingModel | None) -> WalkingSettings | None:
    if model is None:
        return None
    return WalkingSettings(
        speed_kmh=model.speed_kmh,
        max_walk_m=model.max_walk_m,
        max_transfer_walk_m=model.max_transfer_walk_m,
        between_open_stops=model.between_open_stops,
    )


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
    after: TimeMatrix,
) -> NewStops | None:
    """Journeys between open stops that involve at least one added stop."""
    if not new_stop_ids:
        return None
    open_stops = [s for s in [*stop_ids, *new_stop_ids] if s not in closed]
    new = set(new_stop_ids)
    times = [
        after.get(o, d)
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


def table_order(journeys: Sequence[JourneyChange]) -> list[JourneyChange]:
    """Impossible first, then the largest change; ties keep (origin, destination)
    order. The same order as the results table (frontend compareJourneys)."""
    ranked = sorted(
        enumerate(journeys),
        key=lambda item: (item[1].status != "impossible", -abs(item[1].change_min or 0.0), item[0]),
    )
    return [journey for _, journey in ranked]


def _largest_changes(changed: list[JourneyChange], limit: int | None) -> list[JourneyChange]:
    """The first ``limit`` in table order plus the largest still possible ones
    (the chart's), in (origin, destination) order. All of them when they fit."""
    if limit is None or len(changed) <= limit:
        return changed
    keep = {id(j) for j in table_order(changed)[:limit]}
    possible = [j for j in changed if j.change_min is not None]
    possible.sort(key=lambda j: -abs(j.change_min or 0.0))  # stable: ties keep order
    keep |= {id(j) for j in possible[:_CHART_JOURNEYS]}
    return [j for j in changed if id(j) in keep]


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
