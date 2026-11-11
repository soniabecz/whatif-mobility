"""Read the baseline network and turn it into a NetworkX graph.

Graph rules (see docs/IMPLEMENTATION_PLAN.md):
- Stops are nodes, directed connections are edges.
- Edge attribute ``weight`` is the travel time in minutes.
- If several routes connect the same ordered pair of stops, they become ONE
  edge: weight = the fastest travel time, ``routes`` = all serving route ids.
- No transfer penalty: a journey is simply the fastest path.

The graph-building and journey functions take plain data, not a database
session, so they can be tested (and reused by the simulation) without a DB.
"""

from collections.abc import Iterable
from dataclasses import dataclass

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Connection, Route, Stop


class UnknownStopError(ValueError):
    """Raised when a stop id is not part of the network graph."""

    def __init__(self, stop_id: str) -> None:
        super().__init__(f"Unknown stop: {stop_id!r}")
        self.stop_id = stop_id


@dataclass(frozen=True)
class Journey:
    """Fastest path between two stops."""

    stop_ids: list[str]
    travel_time_min: float


# --- Database queries -------------------------------------------------------

def list_stops(db: Session) -> list[Stop]:
    return list(db.scalars(select(Stop).order_by(Stop.id)))


def list_routes(db: Session) -> list[Route]:
    return list(db.scalars(select(Route).order_by(Route.id)))


def list_connections(db: Session) -> list[Connection]:
    return list(db.scalars(select(Connection).order_by(Connection.id)))


# --- Graph ------------------------------------------------------------------

def build_graph(
    stops: Iterable[Stop], connections: Iterable[Connection]
) -> nx.DiGraph:
    """Build the directed network graph from stops and connections."""
    graph = nx.DiGraph()
    for stop in stops:
        graph.add_node(stop.id, name=stop.name, lat=stop.lat, lon=stop.lon)

    for conn in connections:
        for stop_id in (conn.from_stop_id, conn.to_stop_id):
            if stop_id not in graph:
                raise UnknownStopError(stop_id)

        u, v = conn.from_stop_id, conn.to_stop_id
        if graph.has_edge(u, v):
            edge = graph.edges[u, v]
            edge["weight"] = min(edge["weight"], conn.travel_time_min)
            edge["routes"] = sorted({*edge["routes"], conn.route_id})
        else:
            graph.add_edge(u, v, weight=conn.travel_time_min, routes=[conn.route_id])
    return graph


def build_graph_from_db(db: Session) -> nx.DiGraph:
    """Build the baseline graph from the database."""
    return build_graph(list_stops(db), list_connections(db))


def shortest_journey(
    graph: nx.DiGraph, origin_id: str, destination_id: str
) -> Journey | None:
    """Fastest journey from origin to destination.

    Returns None when the destination cannot be reached.
    Raises UnknownStopError when either stop is not in the graph.
    """
    for stop_id in (origin_id, destination_id):
        if stop_id not in graph:
            raise UnknownStopError(stop_id)

    try:
        time, path = nx.single_source_dijkstra(
            graph, origin_id, destination_id, weight="weight"
        )
    except nx.NetworkXNoPath:
        return None
    return Journey(stop_ids=list(path), travel_time_min=float(time))
