"""Read the baseline network and turn it into a NetworkX graph.

Graph rules (see docs/IMPLEMENTATION_PLAN.md):
- Stops are nodes, directed connections are edges.
- Edge attribute ``weight`` is the travel time in minutes.
- If several routes connect the same ordered pair of stops, they become ONE
  edge: weight = the fastest travel time, ``routes`` = all serving route ids,
  ``route_times`` = each route's own time (used by the route graph).
- No transfer penalty: a journey is simply the fastest path.
- Graph attribute ``headways`` = {route id: minutes between buses}; used by
  the route graph for waiting times (stop-level paths ignore it).
  ``route_names`` = {route id: name}, for the AI prompt.

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
    stops: Iterable[Stop],
    connections: Iterable[Connection],
    routes: Iterable[Route] = (),
) -> nx.DiGraph:
    """Build the directed network graph from stops, connections and routes.

    ``routes`` only supply the headways; tests that do not model waiting
    may leave them out.
    """
    routes = list(routes)
    graph = nx.DiGraph(
        headways={route.id: route.headway_min for route in routes},
        route_names={route.id: route.name for route in routes},
    )
    for stop in stops:
        graph.add_node(stop.id, name=stop.name, lat=stop.lat, lon=stop.lon)

    for conn in connections:
        for stop_id in (conn.from_stop_id, conn.to_stop_id):
            if stop_id not in graph:
                raise UnknownStopError(stop_id)

        add_route_edge(
            graph, conn.from_stop_id, conn.to_stop_id, conn.route_id, conn.travel_time_min
        )
    return graph


def add_route_edge(
    graph: nx.DiGraph, u: str, v: str, route_id: str, travel_time_min: float
) -> None:
    """Add one route's u->v connection, merging with an existing edge.

    Edge attributes:
      route_times  {route_id: minutes} -- every route serving u->v
      routes       sorted route ids (convenience copy of route_times keys)
      weight       fastest of route_times (used for shortest paths)

    Attributes are always replaced, never mutated in place, so a shallow
    graph copy can never leak changes back into the original.
    """
    route_times: dict[str, float] = {}
    if graph.has_edge(u, v):
        route_times = dict(graph.edges[u, v]["route_times"])
    current = route_times.get(route_id)
    route_times[route_id] = (
        travel_time_min if current is None else min(current, travel_time_min)
    )
    graph.add_edge(
        u,
        v,
        route_times=route_times,
        routes=sorted(route_times),
        weight=min(route_times.values()),
    )


def build_graph_from_db(db: Session) -> nx.DiGraph:
    """Build the baseline graph from the database."""
    return build_graph(list_stops(db), list_connections(db), list_routes(db))


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
