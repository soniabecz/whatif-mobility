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
from collections.abc import Hashable, Sequence, Set as AbstractSet
from dataclasses import dataclass
from threading import Lock
from typing import Generic, TypeVar

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
    add_joined_link,
    add_pattern,
    add_platform,
    add_ride,
    add_route,
    added_stop_ids,
    build_route_graph,
    has_patterns,
    is_open_stop,
    platforms_of,
    ride_edges,
    route_ids,
    route_rides,
    set_headway,
    TimeMatrix,
)
from app.services.walking import WalkingModel, add_walking_layer, journey_time_matrix

V = TypeVar("V")

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
                    if has_patterns(graph, change.route_id):
                        add_joined_link(graph, change.route_id, u, v, change.travel_time_min)
                    else:
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
        if route_rides(graph, route, u, v)
    ]
    if not legs or legs[0][0] != a:
        raise ScenarioError(f"route '{route}' does not run directly from '{a}' to '{b}'")

    graph.add_node(
        new, kind="stop", name=name, lat=change.lat, lon=change.lon, activity=1, added=True
    )
    for u, v, t_u, t_v in legs:
        for before, after in route_rides(graph, route, u, v):
            graph.remove_edge(before, after)  # buses now stop at the new stop
            if len(before) == 2:  # a route without patterns: shared platforms
                add_ride(graph, u, new, route, t_u)
                add_ride(graph, new, v, route, t_v)
                continue
            # Same pattern, between the two positions (a loop's way back: after the last).
            position, following = before[3], after[3]
            if following <= position:
                following = int(position) + 1
            middle = (new, route, before[2], (position + following) / 2)
            add_platform(graph, middle)
            graph.add_edge(before, middle, kind="ride", route_id=route, weight=t_u)
            graph.add_edge(middle, after, kind="ride", route_id=route, weight=t_v)


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
    graph.graph["patterned_routes"] = graph.graph.get("patterned_routes", frozenset()) | {route}
    stops, times = list(change.stop_ids), list(change.travel_times_min)
    add_pattern(graph, route, 0, stops, times, change.is_loop)
    if change.both_directions:
        # The way back: a loop keeps its first stop; times run in reverse either way.
        back = [stops[0], *reversed(stops[1:])] if change.is_loop else list(reversed(stops))
        add_pattern(graph, route, 1, back, list(reversed(times)), change.is_loop)


def _new_rides(
    graph: nx.DiGraph, change: AddConnection, closed: set[str]
) -> list[tuple[str, str]]:
    """(from, to) pairs an added connection creates; validated before any change."""
    a, b, route = change.from_stop_id, change.to_stop_id, change.route_id
    _require_open_stop(graph, a, closed)
    _require_open_stop(graph, b, closed)
    if route not in route_ids(graph):
        raise ScenarioError(f"unknown route '{route}'")
    if not platforms_of(graph, route, a) and not platforms_of(graph, route, b):
        raise ScenarioError(
            f"route '{route}' stops at neither '{a}' nor '{b}': "
            "a new link must start or end at a stop on the route"
        )
    directions = [(a, b), (b, a)] if change.both_directions else [(a, b)]
    for u, v in directions:
        if route_rides(graph, route, u, v):
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
    exactly the same rules (closed stops, walking, added stops). Immutable:
    states are cached and shared between requests (see scenario_state).
    """

    closed: frozenset[str]
    new_stop_ids: tuple[str, ...]
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
    """Apply the scenario to a copy of the baseline and compute journey times.

    Cached (the last few scenarios per network and settings): downloading the
    CSV, asking for the AI summary or comparing right after a run reuses it.
    Raises ScenarioError for a scenario that does not fit (never cached)."""
    key = (_network_key(baseline, transfer_penalty_min, include_waiting, walking), scenario.model_dump_json())
    cached = _STATE_CACHE.get(key)
    if cached is not None:
        return cached
    graph, closed = apply_scenario(baseline, scenario, transfer_penalty_min, include_waiting)
    new_stop_ids = added_stop_ids(graph)
    add_walking_layer(graph, stop_places(baseline, graph), walking, closed)
    state = ScenarioState(
        closed=frozenset(closed),
        new_stop_ids=tuple(new_stop_ids),
        times=journey_time_matrix(graph, [*sorted(baseline.nodes), *new_stop_ids]),
        walking=walking,
    )
    _STATE_CACHE.put(key, state)
    return state


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


class _LruCache(Generic[V]):
    """A small least-recently-used cache, safe to share between request threads.
    Values must be immutable (they are shared)."""

    def __init__(self, size: int) -> None:
        self._size = size
        self._items: OrderedDict[Hashable, V] = OrderedDict()
        self._lock = Lock()

    def get(self, key: Hashable) -> V | None:
        with self._lock:
            if key not in self._items:
                return None
            self._items.move_to_end(key)
            return self._items[key]

    def put(self, key: Hashable, value: V) -> None:
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self._size:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


# Times on today's network, per network and settings: every simulation needs
# them, and they only change when the network does (e.g. after an import).
_BASELINE_CACHE: _LruCache[TimeMatrix] = _LruCache(4)
# The last few scenarios' journey times (about 4 MB each on the full Gdańsk network).
_STATE_CACHE: _LruCache[ScenarioState] = _LruCache(8)


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
        tuple(sorted(baseline.graph.get("patterns", {}).items())),
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
    cached = _BASELINE_CACHE.get(key)
    if cached is not None:
        return cached
    graph = build_route_graph(baseline, transfer_penalty_min, include_waiting)
    add_walking_layer(graph, baseline, walking, closed=())
    times = journey_time_matrix(graph, sorted(baseline.nodes))
    _BASELINE_CACHE.put(key, times)
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
    k = np.flatnonzero(slower | faster | impossible)  # changed journeys, in (origin, destination) order
    changed = _ChangedJourneys.of(origins[k], destinations[k], t_before[k], t_after[k], has[k])

    count = int(comparable.sum())
    sum_before = _ordered_sum(t_before[comparable])
    sum_after = _ordered_sum(t_after[comparable])
    weighted_comparable = _ordered_sum(weight[comparable])
    weighted_before = _ordered_sum(weight[comparable] * t_before[comparable])
    weighted_after = _ordered_sum(weight[comparable] * t_after[comparable])
    after_times = state.times
    stop_impacts = changed.stop_impacts(stop_ids, closed)
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
        largest_increase=changed.largest_increase(stop_ids),
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
        changed_journeys=changed.listed(stop_ids, max_changed),
        changed_journeys_total=len(changed.change),
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
    new_stop_ids: Sequence[str],
    stop_ids: list[str],
    closed: AbstractSet[str],
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


@dataclass(frozen=True)
class _ChangedJourneys:
    """Every changed journey as arrays, in (origin, destination) order.

    A city has tens of thousands of them, but a result lists about 1,000:
    the figures come from these arrays, and JourneyChange rows are built only
    for the journeys listed. Every value equals what building all rows gave
    (same rounding, same order of addition, same tie-breaking).
    """

    origins: np.ndarray  # stop index
    destinations: np.ndarray
    before: np.ndarray  # minutes, unrounded
    after: np.ndarray  # minutes, unrounded (inf when impossible)
    possible: np.ndarray  # bool: possible after the change
    change: np.ndarray  # rounded change in minutes (NaN when impossible)

    @classmethod
    def of(cls, origins: np.ndarray, destinations: np.ndarray, before: np.ndarray,
           after: np.ndarray, possible: np.ndarray) -> "_ChangedJourneys":
        change = np.full(len(before), np.nan)
        differences = (after[possible] - before[possible]).tolist()
        change[possible] = [_round(d) for d in differences]  # Python's round, as in each row
        return cls(origins, destinations, before, after, possible, change)

    def row(self, i: int, stop_ids: Sequence[str]) -> JourneyChange:
        return _journey_change(
            stop_ids[self.origins[i]], stop_ids[self.destinations[i]],
            float(self.before[i]), float(self.after[i]) if self.possible[i] else None,
        )

    def listed(self, stop_ids: Sequence[str], limit: int | None) -> list[JourneyChange]:
        """The first ``limit`` in table order (see table_order) plus the chart's
        largest still possible ones, in (origin, destination) order; all of them
        when they fit (or ``limit`` is None)."""
        count = len(self.change)
        if limit is None or count <= limit:
            keep = np.arange(count)
        else:
            size = np.where(self.possible, np.abs(np.nan_to_num(self.change)), 0.0)
            table = np.lexsort((np.arange(count), -size, self.possible))  # impossible first
            possible = np.flatnonzero(self.possible)
            chart = possible[np.argsort(-size[possible], kind="stable")[:_CHART_JOURNEYS]]
            keep = np.union1d(table[:limit], chart)
        return [self.row(int(i), stop_ids) for i in keep]

    def largest_increase(self, stop_ids: Sequence[str]) -> JourneyChange | None:
        """The slower journey with the largest (rounded) increase; the first on ties."""
        slower = np.flatnonzero(self.possible & (self.after > self.before))
        if not slower.size:
            return None
        return self.row(int(slower[np.argmax(self.change[slower])]), stop_ids)

    def stop_impacts(self, stop_ids: Sequence[str], closed: AbstractSet[str]) -> list[StopImpact]:
        """Per stop: journeys starting or ending there; the average adds their
        rounded changes in (origin, destination) order."""
        count = len(self.change)
        stops = np.concatenate([self.origins, self.destinations])
        position = np.concatenate([np.arange(count), np.arange(count)])
        grouped = position[np.lexsort((position, stops))]
        bounds = np.concatenate([[0], np.cumsum(np.bincount(stops, minlength=len(stop_ids)))])
        impacts = []
        for index, stop_id in enumerate(stop_ids):
            mine = grouped[bounds[index]:bounds[index + 1]]
            changes = self.change[mine][self.possible[mine]]
            impacts.append(StopImpact(
                stop_id=stop_id,
                closed=stop_id in closed,
                affected_journeys=len(mine),
                impossible_journeys=int((~self.possible[mine]).sum()),
                average_change_min=_round(_ordered_sum(changes) / len(changes)) if len(changes) else None,
            ))
        return impacts


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
