"""Route-aware graph: knows which bus you are on, so changing bus can cost time.

Nodes
  stop id (str)                  where passengers enter, leave and change bus
  (stop id, route id) (tuple)    a "platform": being on that route at that stop

Edges (attribute ``kind``)
  board   stop -> platform        weight = transfer penalty
  alight  platform -> stop        weight = 0
  ride    (u, R) -> (v, R)        weight = route R's own travel time u -> v

Journey time = shortest path stop -> stop MINUS one penalty (the first
boarding is free), so every change of bus adds exactly one penalty.
With a penalty of 0 the times equal those of the stop-level graph.

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


def build_route_graph(network: nx.DiGraph, transfer_penalty_min: float) -> nx.DiGraph:
    """Build the route-aware graph from the stop-level network graph.

    Uses each route's own time from the network edges' ``route_times``.
    The network graph is only read, never modified.
    """
    if transfer_penalty_min < 0:
        raise ValueError("transfer penalty must not be negative")

    graph = nx.DiGraph(transfer_penalty_min=transfer_penalty_min)
    for stop_id, data in network.nodes(data=True):
        graph.add_node(stop_id, kind="stop", **data)

    for u, v, data in sorted(network.edges(data=True), key=lambda edge: (edge[0], edge[1])):
        for route_id, minutes in sorted(data["route_times"].items()):
            for stop_id in (u, v):
                platform = (stop_id, route_id)
                if platform not in graph:
                    graph.add_node(platform, kind="platform", stop_id=stop_id, route_id=route_id)
                    graph.add_edge(stop_id, platform, kind="board", weight=transfer_penalty_min)
                    graph.add_edge(platform, stop_id, kind="alight", weight=0.0)
            graph.add_edge(
                (u, route_id), (v, route_id), kind="ride", route_id=route_id, weight=minutes
            )
    return graph


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
