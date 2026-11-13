"""Walking to or from a closed stop (Day 10, part 3).

Scope: only journeys that start or end at a CLOSED stop use walking. The
passenger walks to a nearby open stop and takes the bus from there (or walks
the whole way if the other stop is within reach). Every other journey is
unchanged, so the route graph and its penalty rule stay as they are; the
walking time is simply added to bus times the graph already computed.

Walking distance = straight line between the stops' coordinates x WALK_DETOUR
(streets are not straight). All walking parameters are invented assumptions.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

import networkx as nx

EARTH_RADIUS_M = 6_371_000
WALK_DETOUR = 1.3  # walking distance / straight-line distance


@dataclass(frozen=True)
class WalkingModel:
    speed_kmh: float  # e.g. 5 km/h
    max_walk_m: float  # longest walk to or from a closed stop

    def minutes(self, distance_m: float) -> float:
        return distance_m / (self.speed_kmh * 1000 / 60)


@dataclass(frozen=True)
class Walk:
    from_stop_id: str
    to_stop_id: str
    distance_m: float
    minutes: float


@dataclass(frozen=True)
class WalkOption:
    """Fastest way between two stops when one or both are closed.

    ``bus_from``/``bus_to`` are None for a walk all the way.
    """

    total_min: float
    walk_start: Walk | None
    walk_end: Walk | None
    bus_from: str | None
    bus_to: str | None


def straight_line_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (haversine)."""
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(h))


def walking_distance_m(network: nx.DiGraph, a: str, b: str) -> float:
    na, nb = network.nodes[a], network.nodes[b]
    return straight_line_m(na["lat"], na["lon"], nb["lat"], nb["lon"]) * WALK_DETOUR


def _walk(network: nx.DiGraph, model: WalkingModel, a: str, b: str) -> Walk | None:
    """The walk a -> b, or None if it is longer than the maximum."""
    distance = walking_distance_m(network, a, b)
    if distance > model.max_walk_m:
        return None
    return Walk(a, b, distance, model.minutes(distance))


def nearby_open_stops(
    network: nx.DiGraph, model: WalkingModel, stop_id: str, closed: Iterable[str]
) -> list[Walk]:
    """Walks from ``stop_id`` to every open stop within reach, sorted by stop id."""
    closed_set = set(closed)
    walks = (
        _walk(network, model, stop_id, other)
        for other in sorted(network.nodes)
        if other != stop_id and other not in closed_set
    )
    return [walk for walk in walks if walk is not None]


def best_walk_option(
    network: nx.DiGraph,
    model: WalkingModel,
    origin: str,
    destination: str,
    closed: set[str],
    bus_time: Callable[[str, str], float | None],
    nearby: Callable[[str], list[Walk]] | None = None,
) -> WalkOption | None:
    """Fastest walk + bus (+ walk) for a journey touching a closed stop, or None.

    ``bus_time(a, b)``: fastest time between two OPEN stops after the
    scenario (None if unreachable). Ties are broken by stop ids, so the
    simulation and the journey explorer always pick the same option.
    ``nearby(stop)``: ``nearby_open_stops`` for this network and closure, if the
    caller keeps them (they depend only on the stop; a city has many journeys).
    """
    if nearby is None:
        nearby = lambda stop: nearby_open_stops(network, model, stop, closed)  # noqa: E731
    candidates: list[tuple[float, str, str, WalkOption]] = []

    # Walk the whole way (both stops may be closed).
    direct = _walk(network, model, origin, destination)
    if direct is not None:
        candidates.append((direct.minutes, "", "", WalkOption(direct.minutes, direct, None, None, None)))

    starts: list[tuple[str, Walk | None]] = (
        [(w.to_stop_id, w) for w in nearby(origin)]
        if origin in closed
        else [(origin, None)]
    )
    ends: list[tuple[str, Walk | None]] = (
        [(w.to_stop_id, _reverse(w)) for w in nearby(destination)]
        if destination in closed
        else [(destination, None)]
    )
    for bus_from, walk_start in starts:
        for bus_to, walk_end in ends:
            if bus_from == bus_to:
                continue  # walking via a stop without riding: the direct walk covers it
            ride = bus_time(bus_from, bus_to)
            if ride is None:
                continue
            total = ride + (walk_start.minutes if walk_start else 0) + (walk_end.minutes if walk_end else 0)
            option = WalkOption(total, walk_start, walk_end, bus_from, bus_to)
            candidates.append((total, bus_from, bus_to, option))

    if not candidates:
        return None
    return min(candidates, key=lambda c: (c[0], c[1], c[2]))[3]


def _reverse(walk: Walk) -> Walk:
    """A walk computed from the destination, turned to arrive there."""
    return Walk(walk.to_stop_id, walk.from_stop_id, walk.distance_m, walk.minutes)
