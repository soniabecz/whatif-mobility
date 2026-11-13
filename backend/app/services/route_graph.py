"""Route-aware graph: knows which bus you are on, so changing bus can cost time.

Nodes
  stop id (str)                  where passengers enter, leave and change bus
  (stop id, route id) (tuple)    a "platform": being on that route at that stop

Edges (attribute ``kind``)
  board   stop -> platform        weight = transfer penalty + wait for route R
  alight  platform -> stop        weight = 0
  ride    (u, R) -> (v, R)        weight = route R's own travel time u -> v

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

Platform = tuple[str, str]  # (stop id, route id)


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

    for u, v, data in sorted(network.edges(data=True), key=lambda edge: (edge[0], edge[1])):
        for route_id, minutes in sorted(data["route_times"].items()):
            add_ride(graph, u, v, route_id, minutes)
    return graph


def add_platform(graph: nx.DiGraph, stop_id: str, route_id: str) -> None:
    """Let ``route_id`` stop at ``stop_id`` (board/alight edges), if it does not yet.

    The wait uses the route's current headway in this graph.
    """
    platform = (stop_id, route_id)
    if platform in graph:
        return
    penalty: float = graph.graph["transfer_penalty_min"]
    wait = _wait_min(graph.graph["headways"], route_id) if graph.graph["include_waiting"] else 0.0
    graph.add_node(platform, kind="platform", stop_id=stop_id, route_id=route_id)
    graph.add_edge(
        stop_id, platform, kind="board", route_id=route_id,
        wait_min=wait, penalty_min=penalty, weight=penalty + wait,
    )
    graph.add_edge(platform, stop_id, kind="alight", weight=0.0)


def add_ride(graph: nx.DiGraph, u: str, v: str, route_id: str, minutes: float) -> None:
    """Route ``route_id`` runs directly u -> v in ``minutes`` (platforms added as needed)."""
    add_platform(graph, u, route_id)
    add_platform(graph, v, route_id)
    graph.add_edge((u, route_id), (v, route_id), kind="ride", route_id=route_id, weight=minutes)


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
    """Ride edges of every route that runs directly from_stop -> to_stop."""
    return sorted(
        ((from_stop, route_id), (to_stop, route_id))
        for (_, route_id) in graph.successors(from_stop)
        if graph.has_edge((from_stop, route_id), (to_stop, route_id))
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
