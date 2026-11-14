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
  ``route_names`` = {route id: name} and ``route_colors`` = {route id: colour},
  for the AI prompt.

The graph-building and journey functions take plain data, not a database
session, so they can be tested (and reused by the simulation) without a DB.
"""

from collections.abc import Iterable
from dataclasses import dataclass

import networkx as nx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Connection, NetworkSource, PatternStop, Route, RoutePattern, Stop


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


@dataclass(frozen=True)
class Pattern:
    """One way a route's vehicles run (see models.RoutePattern)."""

    route_id: str
    stop_ids: tuple[str, ...]
    is_loop: bool = False

    def stretches(self) -> list[tuple[str, str]]:
        """(from, to) of every stretch driven, the loop's way back included."""
        pairs = list(zip(self.stop_ids, self.stop_ids[1:]))
        return [*pairs, (self.stop_ids[-1], self.stop_ids[0])] if self.is_loop else pairs


def list_patterns(db: Session) -> list[Pattern]:
    """Every route's patterns, in route and number order."""
    rows = db.execute(
        select(RoutePattern.route_id, RoutePattern.number, RoutePattern.is_loop, PatternStop.stop_id)
        .join(PatternStop, PatternStop.pattern_id == RoutePattern.id)
        .order_by(RoutePattern.route_id, RoutePattern.number, PatternStop.position)
    ).all()
    grouped: dict[tuple[str, int], tuple[bool, list[str]]] = {}
    for route_id, number, is_loop, stop_id in rows:
        grouped.setdefault((route_id, number), (is_loop, []))[1].append(stop_id)
    return [Pattern(route_id, tuple(stops), is_loop) for (route_id, _), (is_loop, stops) in grouped.items()]


def add_patterns(db: Session, route_id: str, patterns: Iterable[tuple[Iterable[str], bool]]) -> None:
    """Store a route's patterns (numbered in the given order). Caller commits."""
    for number, (stop_ids, is_loop) in enumerate(patterns):
        pattern = RoutePattern(route_id=route_id, number=number, is_loop=is_loop)
        db.add(pattern)
        db.flush()  # the id is needed for the stops
        for position, stop_id in enumerate(stop_ids):
            db.add(PatternStop(pattern_id=pattern.id, position=position, stop_id=stop_id))


def delete_network(db: Session) -> None:
    """Delete every network table's rows, children first (foreign keys). Caller commits."""
    for model in (PatternStop, RoutePattern, Connection, Route, Stop, NetworkSource):
        db.execute(delete(model))


def get_source(db: Session) -> NetworkSource | None:
    """The real network's data source, or None for the invented sample."""
    return db.scalars(select(NetworkSource).limit(1)).first()


# --- Graph ------------------------------------------------------------------

def build_graph(
    stops: Iterable[Stop],
    connections: Iterable[Connection],
    routes: Iterable[Route] = (),
    patterns: Iterable[Pattern] = (),
) -> nx.DiGraph:
    """Build the directed network graph from stops, connections and routes.

    ``routes`` only supply the headways; tests that do not model waiting
    may leave them out. ``patterns``: how each route's vehicles run (graph
    attribute ``patterns``, route id -> tuple of Pattern); a route without
    patterns is treated as before Day 14 part 4. Every stretch of a pattern
    must be a connection of its route.
    """
    routes = list(routes)
    graph = nx.DiGraph(
        headways={route.id: route.headway_min for route in routes},
        route_names={route.id: route.name for route in routes},
        route_colors={route.id: route.color for route in routes},
    )
    for stop in stops:
        # activity: missing (stops built in tests) counts as 1, i.e. equal weights.
        graph.add_node(
            stop.id, name=stop.name, lat=stop.lat, lon=stop.lon, activity=stop.activity or 1
        )

    for conn in connections:
        for stop_id in (conn.from_stop_id, conn.to_stop_id):
            if stop_id not in graph:
                raise UnknownStopError(stop_id)

        add_route_edge(
            graph, conn.from_stop_id, conn.to_stop_id, conn.route_id, conn.travel_time_min
        )

    by_route: dict[str, list[Pattern]] = {}
    for pattern in patterns:
        for piece in _runnable_pieces(graph, pattern):
            by_route.setdefault(pattern.route_id, []).append(piece)
    graph.graph["patterns"] = {route_id: tuple(found) for route_id, found in by_route.items()}
    return graph


def _runnable_pieces(graph: nx.DiGraph, pattern: Pattern) -> list[Pattern]:
    """The pattern split where a stretch is not a connection of its route (the
    data was edited); unchanged when every stretch exists."""
    def runs(u: str, v: str) -> bool:
        return graph.has_edge(u, v) and pattern.route_id in graph.edges[u, v]["route_times"]

    stretches = pattern.stretches()
    if all(runs(u, v) for u, v in stretches):
        return [pattern]
    if pattern.is_loop:  # start the loop's stops just after a missing stretch
        gap = next(i for i, (u, v) in enumerate(stretches) if not runs(u, v))
        stretches = stretches[gap + 1:] + stretches[:gap + 1]
    pieces: list[list[str]] = []
    current: list[str] = []
    for u, v in stretches:
        if runs(u, v):
            current = current or [u]
            current.append(v)
        elif current:
            pieces.append(current)
            current = []
    if current:
        pieces.append(current)
    return [Pattern(pattern.route_id, tuple(stops)) for stops in pieces]


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
    return build_graph(list_stops(db), list_connections(db), list_routes(db), list_patterns(db))


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
