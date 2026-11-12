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

from dataclasses import dataclass

import networkx as nx

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
    )
    for stop_id, data in network.nodes(data=True):
        graph.add_node(stop_id, kind="stop", **data)

    for u, v, data in sorted(network.edges(data=True), key=lambda edge: (edge[0], edge[1])):
        for route_id, minutes in sorted(data["route_times"].items()):
            for stop_id in (u, v):
                platform = (stop_id, route_id)
                if platform not in graph:
                    graph.add_node(platform, kind="platform", stop_id=stop_id, route_id=route_id)
                    wait = _wait_min(headways, route_id) if include_waiting else 0.0
                    graph.add_edge(
                        stop_id, platform, kind="board", route_id=route_id,
                        wait_min=wait, penalty_min=transfer_penalty_min,
                        weight=transfer_penalty_min + wait,
                    )
                    graph.add_edge(platform, stop_id, kind="alight", weight=0.0)
            graph.add_edge(
                (u, route_id), (v, route_id), kind="ride", route_id=route_id, weight=minutes
            )
    return graph


def _wait_min(headways: dict[str, float], route_id: str) -> float:
    """Expected wait for a passenger arriving at random: half the headway."""
    if route_id not in headways:
        raise ValueError(f"no headway for route '{route_id}': cannot include waiting")
    return headways[route_id] / 2


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


def fastest_path(graph: nx.DiGraph, origin: str, destination: str) -> RoutePath | None:
    """Fastest path between two open stops, or None if unreachable."""
    try:
        distance, nodes = nx.single_source_dijkstra(graph, origin, destination, weight="weight")
    except nx.NetworkXNoPath:
        return None
    return RoutePath(nodes=list(nodes), travel_time_min=distance - graph.graph["transfer_penalty_min"])
