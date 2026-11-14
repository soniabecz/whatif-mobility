"""Walking as part of the route graph (Day 10 part 3; Day 14 walking between stops).

The route graph (route_graph.py) knows only buses. ``add_walking_layer`` adds a
few nodes per stop for the passenger's situation, so ONE shortest-path search
finds journeys that walk at the start, between two buses or at the end:

  start(s)    the journey begins at s, nothing boarded yet. Enters stop s
              (free) to board there, or walks once (to walked(t)).
  walked(t)   walked from the start to t. Boards at t; cannot walk again. It is
              also how a journey walks the whole way.
  stop t      (the route graph's own node) boards there; reached from start(t),
              by getting off a bus at t, or by walking to t between two buses.
              Cannot walk.
  off(t)      got off at t, reached only by RIDING to t (every ride edge into t
              has a copy ending here). Walks once: to end(u), or between two
              buses to stop u. Walks start here, not at stop t, because stop t
              can also be reached without riding, which would chain two walks.
  end(u)      walked to u after the last bus. The journey ends here.

Every boarding is counted as a change of bus (the penalty); the first one is
subtracted at the end. A walk between buses is never longer than a walk at the
end (``WalkingModel`` checks it), so arriving at stop u after such a walk takes
exactly as long as arriving at end(u).

So there is at most one walk in a row: at the start, between buses and at the
end, never two walks chained into a longer one. Journey time from s to d =
the fastest of: stop d or end(d) minus one transfer penalty (the first
boarding is no change of bus; see route_graph.py), or walked(d) (no bus).

Closed stops keep their start, walked and end nodes (passengers walk away from
or to them), but nobody boards there: their stop node and board edges are gone.

``WalkingModel.between_open_stops`` False keeps the Day 10 rule: walking only
from or to a CLOSED stop (at the start or end), never between two buses.

Walking distance = straight line between the stops' coordinates x WALK_DETOUR
(streets are not straight). All walking parameters are invented assumptions.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import Literal

import networkx as nx
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from app.services.route_graph import TimeMatrix, is_open_stop

EARTH_RADIUS_M = 6_371_000
WALK_DETOUR = 1.3  # walking distance / straight-line distance

_EPSILON = 1e-9  # two times closer than this are equal (as in the simulation)

WalkKind = Literal["start", "walked", "off", "end"]


@dataclass(frozen=True)
class WalkingModel:
    speed_kmh: float  # e.g. 5 km/h
    max_walk_m: float  # longest walk at the start or end of a journey
    max_transfer_walk_m: float = 500.0  # longest walk between two buses
    between_open_stops: bool = True  # False: walk only from/to a closed stop (Day 10)

    def __post_init__(self) -> None:
        if self.max_transfer_walk_m > self.max_walk_m:
            raise ValueError("a walk between buses cannot be longer than a walk at the start or end")

    def minutes(self, distance_m: float) -> float:
        return distance_m / (self.speed_kmh * 1000 / 60)


@dataclass(frozen=True)
class Walk:
    from_stop_id: str
    to_stop_id: str
    distance_m: float
    minutes: float


@dataclass(frozen=True, order=True)
class WalkNode:
    """A passenger's situation at a stop (see the module docstring)."""

    kind: WalkKind
    stop_id: str


def straight_line_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (haversine)."""
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(h))


def walking_distance_m(places: nx.DiGraph, a: str, b: str) -> float:
    na, nb = places.nodes[a], places.nodes[b]
    return straight_line_m(na["lat"], na["lon"], nb["lat"], nb["lon"]) * WALK_DETOUR


def walks_within(places: nx.DiGraph, stop_ids: Sequence[str], model: WalkingModel) -> list[Walk]:
    """Every walk a -> b (a != b) of at most ``model.max_walk_m``, in (a, b) order.

    A vectorised pre-selection finds the candidates; each distance is then
    computed exactly as ``walking_distance_m`` (so it never depends on numpy's
    rounding).
    """
    if len(stop_ids) < 2:
        return []
    lat = np.radians([places.nodes[s]["lat"] for s in stop_ids])
    lon = np.radians([places.nodes[s]["lon"] for s in stop_ids])
    h = (np.sin((lat[:, None] - lat[None, :]) / 2) ** 2
         + np.cos(lat[:, None]) * np.cos(lat[None, :]) * np.sin((lon[:, None] - lon[None, :]) / 2) ** 2)
    rough = 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(h, 0, 1))) * WALK_DETOUR
    walks = []
    max_m = model.max_walk_m
    for i, j in zip(*np.nonzero(rough <= max_m + 1.0)):  # 1 m margin for rounding
        if i == j:
            continue
        a, b = stop_ids[i], stop_ids[j]
        distance = walking_distance_m(places, a, b)
        if distance <= max_m:
            walks.append(Walk(a, b, distance, model.minutes(distance)))
    return walks


def add_walking_layer(
    graph: nx.DiGraph,
    places: nx.DiGraph,
    model: WalkingModel | None,
    closed: Iterable[str],
) -> None:
    """Add the start/walked/off/end nodes and walks to a route graph (in place).

    ``places``: every stop with coordinates, closed ones included (baseline
    stops plus stops added by the scenario). ``model`` None: no walking at all
    (only the start nodes, so journeys can still be searched from them).
    Call it after all of a scenario's changes: the boarding copies take the
    board edges (and waits) as they are then.
    """
    closed_set = set(closed)
    stop_ids = sorted(places.nodes)
    boards = {
        s: [(platform, dict(data)) for _, platform, data in graph.out_edges(s, data=True)
            if data["kind"] == "board"]
        for s in stop_ids if is_open_stop(graph, s)
    }

    def add_boarding(node: WalkNode, stop_id: str) -> None:
        graph.add_node(node, kind=node.kind, stop_id=stop_id)
        for platform, data in boards.get(stop_id, []):
            graph.add_edge(node, platform, **data)

    for s in stop_ids:
        start = WalkNode("start", s)
        graph.add_node(start, kind="start", stop_id=s)
        if s in boards:  # open: board at the stop itself
            graph.add_edge(start, s, kind="enter", weight=0.0)
    if model is None:
        return
    rides = [(u, v, data) for u, v, data in graph.edges(data=True) if data["kind"] == "ride"]
    for u, v, data in rides:
        if v[0] in boards:  # nobody gets off at a closed stop
            graph.add_edge(u, WalkNode("off", v[0]), **data)
    for s in stop_ids:
        add_boarding(WalkNode("walked", s), s)
        graph.add_node(WalkNode("end", s), kind="end", stop_id=s)

    def add_walk(from_node: object, to_node: object, walk: Walk) -> None:
        graph.add_edge(
            from_node, to_node, kind="walk", distance_m=walk.distance_m,
            minutes=walk.minutes, weight=walk.minutes,
        )

    for walk in walks_within(places, stop_ids, model):
        a, b = walk.from_stop_id, walk.to_stop_id
        touches_closed = a in closed_set or b in closed_set
        if model.between_open_stops or touches_closed:
            add_walk(WalkNode("start", a), WalkNode("walked", b), walk)
        off = WalkNode("off", a)
        if off in graph and (model.between_open_stops or b in closed_set):
            add_walk(off, WalkNode("end", b), walk)
        if (model.between_open_stops and off in graph and b in boards
                and walk.distance_m <= model.max_transfer_walk_m):
            add_walk(off, b, walk)  # between two buses: board again at stop b


def _arrivals(graph: nx.DiGraph, stop_id: str) -> list[tuple[object, bool]]:
    """Nodes where a journey to ``stop_id`` can end, and whether a transfer
    penalty is subtracted (it is, once a bus was boarded)."""
    # On a tie the simplest journey wins: walking the whole way, then by bus.
    candidates: list[tuple[object, bool]] = [
        (WalkNode("walked", stop_id), False), (stop_id, True), (WalkNode("end", stop_id), True),
    ]
    return [
        (node, subtract) for node, subtract in candidates
        if node in graph and (not isinstance(node, str) or is_open_stop(graph, node))
    ]


def journey_time_matrix(graph: nx.DiGraph, stop_ids: Sequence[str]) -> TimeMatrix:
    """Fastest journey times between the given stops in a graph with a walking
    layer (closed stops included: they are reached and left on foot).

    The same compiled Dijkstra as ``route_graph.travel_time_matrix``; journeys
    start at start(s) and end at the fastest of their arrival nodes.
    """
    nodes = list(graph.nodes)
    position = {node: i for i, node in enumerate(nodes)}
    edges = [(position[u], position[v], data["weight"]) for u, v, data in graph.edges(data=True)]
    rows = np.fromiter((e[0] for e in edges), dtype=np.int64, count=len(edges))
    cols = np.fromiter((e[1] for e in edges), dtype=np.int64, count=len(edges))
    weights = np.fromiter((e[2] for e in edges), dtype=float, count=len(edges))
    matrix = csr_matrix((weights, (rows, cols)), shape=(len(nodes), len(nodes)))
    penalty: float = graph.graph["transfer_penalty_min"]

    n = len(stop_ids)
    values = np.full((n, n), np.inf)
    if n:
        sources = [position[WalkNode("start", s)] for s in stop_ids]
        distances = dijkstra(matrix, directed=True, indices=sources)
        for j, stop_id in enumerate(stop_ids):
            for node, subtract in _arrivals(graph, stop_id):
                column = distances[:, position[node]] - (penalty if subtract else 0.0)
                values[:, j] = np.minimum(values[:, j], column)
    np.fill_diagonal(values, 0.0)
    values.setflags(write=False)
    return TimeMatrix(tuple(stop_ids), {s: i for i, s in enumerate(stop_ids)}, values)


@dataclass(frozen=True)
class JourneyPath:
    """Fastest journey in a graph with a walking layer: nodes from start(origin)
    to the arrival node, and the journey time (unrounded)."""

    nodes: list[object]
    travel_time_min: float


def fastest_journey(graph: nx.DiGraph, origin: str, destination: str) -> JourneyPath | None:
    """The fastest journey origin -> destination (same rules as
    ``journey_time_matrix``), or None if there is none."""
    source = WalkNode("start", origin)
    if source not in graph or origin == destination:
        return None
    lengths, paths = nx.single_source_dijkstra(graph, source, weight="weight")
    penalty: float = graph.graph["transfer_penalty_min"]
    best: float | None = None
    best_node: object = None
    # Arrivals in order of preference: a later one must be faster by more than
    # float noise (e.g. "walk" vs "walk, board and get off at once" with no wait).
    for node, subtract in _arrivals(graph, destination):
        if node not in lengths:
            continue
        time = lengths[node] - (penalty if subtract else 0.0)
        if best is None or time < best - _EPSILON:
            best, best_node = time, node
    if best is None:
        return None
    return JourneyPath(nodes=list(paths[best_node]), travel_time_min=best)
