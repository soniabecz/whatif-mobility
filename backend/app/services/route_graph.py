"""Route-aware graph: knows which bus you are on, so changing bus can cost time.

Nodes
  stop id (str)                  where passengers enter, leave and change bus
  platform (tuple)               being on a route's vehicle at a stop:
    (stop, route, pattern, position)  for a route with patterns (Day 14 part 4):
                                 at that position of one of its stop sequences
    (stop, route)                for a route without patterns (shared by
                                 everything the route does at the stop)
  A platform's first two items are always the stop and the route.

Edges (attribute ``kind``)
  board   stop -> platform        weight = transfer penalty + wait for route R
  alight  platform -> stop        weight = 0
  ride    platform -> platform    weight = route R's own travel time u -> v
  stay    platform -> platform    weight = 0; staying on at the same stop onto a
                                  link a scenario added (see add_joined_link)

With patterns, a ride goes only to the NEXT position of the same pattern, so
passengers stay on a vehicle only where a trip really goes: turning round,
switching direction or skipping a loop the vehicle drives means getting off
and boarding again. Without patterns any two rides of the route at a stop
connect (the model before Day 14 part 4).

Waiting (``include_waiting``): passengers arrive at random, so they wait on
average half of route R's headway at EVERY boarding, the first included.
Board edges keep ``wait_min`` and ``penalty_min`` separately for the
journey explorer's breakdown.

Journey time = shortest path stop -> stop MINUS one penalty (the first
boarding has no transfer penalty), so
    time = in-vehicle + waiting at every boarding + penalty x changes of bus.
Without waiting and with a penalty of 0 the times equal those of the
stop-level graph; without waiting they equal the engine before Day 10.

Closing a stop removes only the stop node (and its board/alight edges):
the ride edges through its platforms remain, so buses drive through it,
but nobody can board, alight or change bus there.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import networkx as nx
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

Platform = tuple  # (stop, route) or (stop, route, pattern, position); see above


@dataclass(frozen=True)
class RoutePath:
    """Fastest path: graph nodes in order and the journey time (unrounded)."""

    nodes: list[str | Platform]
    travel_time_min: float


def build_route_graph(
    network: nx.DiGraph, transfer_penalty_min: float, include_waiting: bool = False
) -> nx.DiGraph:
    """Build the route-aware graph from the stop-level network graph.

    Uses each route's own time from the network edges' ``route_times`` and,
    with ``include_waiting``, its headway from the graph's ``headways``.
    The network graph is only read, never modified.
    """
    if transfer_penalty_min < 0:
        raise ValueError("transfer penalty must not be negative")
    headways: dict[str, float] = dict(network.graph.get("headways", {}))

    graph = nx.DiGraph(
        transfer_penalty_min=transfer_penalty_min,
        include_waiting=include_waiting,
        headways=headways,
        # Copied so that names of routes added by a scenario stay in this graph.
        route_names=dict(network.graph.get("route_names", {})),
    )
    for stop_id, data in network.nodes(data=True):
        graph.add_node(stop_id, kind="stop", **data)

    patterns: dict[str, tuple] = network.graph.get("patterns", {})
    graph.graph["patterned_routes"] = frozenset(patterns)
    covered: set[tuple[str, str, str]] = set()
    next_number: dict[str, int] = {}
    for route_id in sorted(patterns):
        for number, pattern in enumerate(patterns[route_id]):
            times = [network.edges[u, v]["route_times"][route_id] for u, v in pattern.stretches()]
            add_pattern(graph, route_id, number, list(pattern.stop_ids), times, pattern.is_loop)
            covered.update((route_id, u, v) for u, v in pattern.stretches())
        next_number[route_id] = len(patterns[route_id])

    for u, v, data in sorted(network.edges(data=True), key=lambda edge: (edge[0], edge[1])):
        for route_id, minutes in sorted(data["route_times"].items()):
            if route_id not in patterns:
                add_ride(graph, u, v, route_id, minutes)
            elif (route_id, u, v) not in covered:
                # A link of a route with patterns that no pattern drives (edited
                # data): ridable on its own, with no staying on before or after.
                add_pattern(graph, route_id, next_number[route_id], [u, v], [minutes], False)
                next_number[route_id] += 1
    return graph


def add_pattern(
    graph: nx.DiGraph,
    route_id: str,
    number: int,
    stop_ids: Sequence[str],
    minutes: Sequence[float],
    is_loop: bool,
) -> None:
    """Platforms (stop, route, number, position) along one stop sequence, with
    rides to the next position (and from the last back to the first for a loop).
    ``minutes[i]`` is the time from position i to the next."""
    platforms = [(stop_id, route_id, number, position) for position, stop_id in enumerate(stop_ids)]
    for platform in platforms:
        add_platform(graph, platform)
    pairs = list(zip(platforms, platforms[1:]))
    if is_loop:
        pairs.append((platforms[-1], platforms[0]))
    for (a, b), time in zip(pairs, minutes, strict=True):
        graph.add_edge(a, b, kind="ride", route_id=route_id, weight=time)


def add_platform(graph: nx.DiGraph, platform: Platform) -> None:
    """Add a platform (stop, route, ...) with board/alight edges, if it does not exist.

    The wait uses the route's current headway in this graph.
    """
    if platform in graph:
        return
    stop_id, route_id = platform[0], platform[1]
    penalty: float = graph.graph["transfer_penalty_min"]
    wait = _wait_min(graph.graph["headways"], route_id) if graph.graph["include_waiting"] else 0.0
    graph.add_node(platform, kind="platform", stop_id=stop_id, route_id=route_id)
    graph.add_edge(
        stop_id, platform, kind="board", route_id=route_id,
        wait_min=wait, penalty_min=penalty, weight=penalty + wait,
    )
    graph.add_edge(platform, stop_id, kind="alight", weight=0.0)


def add_ride(graph: nx.DiGraph, u: str, v: str, route_id: str, minutes: float) -> None:
    """Route ``route_id`` (without patterns) runs directly u -> v in ``minutes``,
    on its shared platforms (added as needed)."""
    add_platform(graph, (u, route_id))
    add_platform(graph, (v, route_id))
    graph.add_edge((u, route_id), (v, route_id), kind="ride", route_id=route_id, weight=minutes)


def has_patterns(graph: nx.DiGraph, route_id: str) -> bool:
    return route_id in graph.graph.get("patterned_routes", frozenset())


def platforms_of(graph: nx.DiGraph, route_id: str, stop_id: str) -> list[Platform]:
    """Every platform of the route at the stop (also at a closed stop), sorted."""
    return sorted(
        node for node, data in graph.nodes(data=True)
        if isinstance(node, tuple) and node[0] == stop_id and node[1] == route_id
    )


def route_rides(graph: nx.DiGraph, route_id: str, from_stop: str, to_stop: str) -> list[tuple[Platform, Platform]]:
    """The route's ride edges from_stop -> to_stop (one per pattern that runs it)."""
    return sorted(
        (a, b)
        for a in platforms_of(graph, route_id, from_stop)
        for b in graph.successors(a)
        if isinstance(b, tuple) and b[0] == to_stop and graph.edges[a, b]["kind"] == "ride"
    )


def _added_link_part(platform: Platform) -> int | None:
    """0 / 1 for the start / end platform of a link added by add_joined_link
    (negative pattern numbers); None for any other platform."""
    return platform[3] if len(platform) == 4 and platform[2] < 0 else None


def add_joined_link(graph: nx.DiGraph, route_id: str, u: str, v: str, minutes: float) -> None:
    """A scenario adds the link u -> v to a route WITH patterns. It joins the
    route at both ends: a passenger on the route's vehicle at u (on a pattern,
    or arriving on another added link) may stay on onto it, and at v stay on
    along any of the route's patterns or onto another added link from v.
    The link gets its own pattern number (negative: -1, -2, ...)."""
    number = -1 - sum(
        1 for node in graph.nodes
        if isinstance(node, tuple) and node[1] == route_id and _added_link_part(node) == 0
    )
    start, end = (u, route_id, number, 0), (v, route_id, number, 1)
    add_platform(graph, start)
    add_platform(graph, end)
    graph.add_edge(start, end, kind="ride", route_id=route_id, weight=minutes)
    for platform in platforms_of(graph, route_id, u):
        if _added_link_part(platform) != 0:  # not another added link's start
            graph.add_edge(platform, start, kind="stay", route_id=route_id, weight=0.0)
    for platform in platforms_of(graph, route_id, v):
        if platform != end and _added_link_part(platform) != 1:  # not an added link's end
            graph.add_edge(end, platform, kind="stay", route_id=route_id, weight=0.0)


def add_route(graph: nx.DiGraph, route_id: str, name: str, headway_min: float) -> None:
    """Register a new route (name and headway) before its rides are added,
    so its board edges get the right wait. Only for a scenario's graph."""
    graph.graph["headways"] = {**graph.graph["headways"], route_id: headway_min}
    graph.graph["route_names"] = {**graph.graph.get("route_names", {}), route_id: name}


def route_ids(graph: nx.DiGraph) -> set[str]:
    """Routes that serve at least one stop (they have platforms)."""
    return {node[1] for node in graph.nodes if isinstance(node, tuple)}


def set_headway(graph: nx.DiGraph, route_id: str, headway_min: float) -> None:
    """Give a route a new headway: updates the wait on its board edges.

    Only for a route graph built for one scenario (never the baseline).
    Without waiting the wait stays 0, so times do not change.
    """
    headways = dict(graph.graph["headways"])
    headways[route_id] = headway_min
    graph.graph["headways"] = headways
    if not graph.graph["include_waiting"]:
        return
    wait = _wait_min(headways, route_id)
    for _, _, data in graph.edges(data=True):
        if data["kind"] == "board" and data["route_id"] == route_id:
            data["wait_min"] = wait
            data["weight"] = data["penalty_min"] + wait


def _wait_min(headways: dict[str, float], route_id: str) -> float:
    """Expected wait for a passenger arriving at random: half the headway."""
    if route_id not in headways:
        raise ValueError(f"no headway for route '{route_id}': cannot include waiting")
    return headways[route_id] / 2


def added_stop_ids(graph: nx.DiGraph) -> list[str]:
    """Stops added by the scenario (and still open), sorted."""
    return sorted(
        node for node, data in graph.nodes(data=True)
        if isinstance(node, str) and data.get("added", False)
    )


def is_open_stop(graph: nx.DiGraph, node: object) -> bool:
    """True for a stop node that still exists (closed stops are removed)."""
    return isinstance(node, str) and node in graph and graph.nodes[node]["kind"] == "stop"


def stop_ids(graph: nx.DiGraph) -> list[str]:
    """Open stops, sorted."""
    return sorted(node for node in graph.nodes if isinstance(node, str))


def ride_edges(graph: nx.DiGraph, from_stop: str, to_stop: str) -> list[tuple[Platform, Platform]]:
    """Ride edges of every route (and pattern) that runs directly from_stop -> to_stop."""
    return sorted(
        (a, b)
        for a in graph.successors(from_stop)
        if isinstance(a, tuple)
        for b in graph.successors(a)
        if isinstance(b, tuple) and b[0] == to_stop and graph.edges[a, b]["kind"] == "ride"
    )


def travel_times_from(graph: nx.DiGraph, origin: str) -> dict[str, float]:
    """Fastest journey time from ``origin`` to every reachable open stop."""
    penalty: float = graph.graph["transfer_penalty_min"]
    lengths = nx.single_source_dijkstra_path_length(graph, origin, weight="weight")
    return {
        node: distance - penalty
        for node, distance in lengths.items()
        if isinstance(node, str) and node != origin
    }


@dataclass(frozen=True)
class TimeMatrix:
    """Fastest journey times between stops: ``values[i, j]`` from ``stop_ids[i]``
    to ``stop_ids[j]`` (inf = unreachable; the diagonal is 0). Read-only."""

    stop_ids: tuple[str, ...]
    index: dict[str, int]
    values: np.ndarray

    def get(self, origin: str, destination: str) -> float | None:
        """Like ``travel_times_from(graph, origin).get(destination)``."""
        i, j = self.index.get(origin), self.index.get(destination)
        if i is None or j is None or i == j:
            return None
        value = float(self.values[i, j])
        return None if value == np.inf else value


def travel_time_matrix(graph: nx.DiGraph, origins: Sequence[str]) -> TimeMatrix:
    """Fastest times between the given open stops, all at once.

    Same result as ``travel_times_from`` for each origin (both run Dijkstra on
    this graph's weights; checked to be identical), but in compiled code: about
    20x faster on a real city. Explicit zero weights (alighting) are kept as edges.
    """
    nodes = list(graph.nodes)
    position = {node: i for i, node in enumerate(nodes)}
    edges = [(position[u], position[v], data["weight"]) for u, v, data in graph.edges(data=True)]
    rows = np.fromiter((e[0] for e in edges), dtype=np.int64, count=len(edges))
    cols = np.fromiter((e[1] for e in edges), dtype=np.int64, count=len(edges))
    weights = np.fromiter((e[2] for e in edges), dtype=float, count=len(edges))
    matrix = csr_matrix((weights, (rows, cols)), shape=(len(nodes), len(nodes)))
    columns = [position[s] for s in origins]
    if columns:
        distances = dijkstra(matrix, directed=True, indices=columns)[:, columns]
    else:
        distances = np.zeros((0, 0))
    # The first boarding has no transfer penalty (see the module docstring).
    values = distances - graph.graph["transfer_penalty_min"]
    np.fill_diagonal(values, 0.0)
    values.setflags(write=False)
    return TimeMatrix(tuple(origins), {s: i for i, s in enumerate(origins)}, values)


def fastest_path(graph: nx.DiGraph, origin: str, destination: str) -> RoutePath | None:
    """Fastest path between two open stops, or None if unreachable."""
    try:
        distance, nodes = nx.single_source_dijkstra(graph, origin, destination, weight="weight")
    except nx.NetworkXNoPath:
        return None
    return RoutePath(nodes=list(nodes), travel_time_min=distance - graph.graph["transfer_penalty_min"])
