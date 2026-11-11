"""The invented sample city used by the MVP.

Layout (grid units, x = east, y = north; Central Station at the origin):

               NTH
                |
        OLD -- UNI -- MUS            R1 Red    North–South line
         |      |      |             R2 Blue   East–West line
         |     MKT     |             R3 Green  Ring (loop)
         |      |      |             R4 Orange Airport Express
  WST -- LIB -- CEN -- RIV -- EST
         |      |      |
        SCH -- HOS -- STD -- TEC
                |              :
               STH            AIR

  (R4 also runs MKT-CEN and a direct diagonal CEN-STD, then TEC-AIR.)

Hubs: CEN (all four lines), plus several two-line transfer stops, so
closing a stop or removing a link changes journeys in interesting ways.

Every segment is served in both directions with the same travel time.
Data is invented; the coordinates only place it on a real map background.
To move the city, change CITY_CENTER.
"""

from dataclasses import dataclass

CITY_CENTER: tuple[float, float] = (50.0614, 19.9366)  # (lat, lon)
GRID_STEP_LAT = 0.0060  # ≈ 670 m
GRID_STEP_LON = 0.0090  # ≈ 640 m at this latitude


@dataclass(frozen=True)
class SampleStop:
    id: str
    name: str
    x: float
    y: float


@dataclass(frozen=True)
class SampleRoute:
    id: str
    name: str
    color: str
    stop_ids: list[str]
    # travel_times_min[i] is the time between stop_ids[i] and stop_ids[i+1];
    # for a loop, the last entry is the time back to the first stop.
    travel_times_min: list[float]
    is_loop: bool = False


STOPS: list[SampleStop] = [
    SampleStop("CEN", "Central Station", 0, 0),
    SampleStop("MKT", "Market Square", 0, 1),
    SampleStop("UNI", "University", 0, 2),
    SampleStop("NTH", "North Park", 0, 3),
    SampleStop("HOS", "City Hospital", 0, -1),
    SampleStop("STH", "South Terminal", 0, -2),
    SampleStop("LIB", "Library", -1, 0),
    SampleStop("WST", "West End", -2, 0),
    SampleStop("RIV", "Riverside", 1, 0),
    SampleStop("EST", "East Gate", 2, 0),
    SampleStop("MUS", "Museum", 1, 2),
    SampleStop("OLD", "Old Town", -1, 2),
    SampleStop("SCH", "School Lane", -1, -1),
    SampleStop("STD", "Stadium", 1, -1),
    SampleStop("TEC", "Tech Park", 2, -1),
    SampleStop("AIR", "Airport", 3, -2),
]

ROUTES: list[SampleRoute] = [
    SampleRoute(
        "R1", "North–South", "#dc2626",
        ["NTH", "UNI", "MKT", "CEN", "HOS", "STH"],
        [4, 3, 3, 4, 5],
    ),
    SampleRoute(
        "R2", "East–West", "#2563eb",
        ["WST", "LIB", "CEN", "RIV", "EST"],
        [5, 4, 4, 5],
    ),
    SampleRoute(
        "R3", "Ring", "#16a34a",
        ["UNI", "MUS", "RIV", "STD", "HOS", "SCH", "LIB", "OLD"],
        [3, 4, 3, 3, 4, 3, 3, 3],
        is_loop=True,
    ),
    # Shares MKT–CEN with R1 but is faster (fewer stops on the street),
    # which exercises the "parallel connections" rule in the graph.
    SampleRoute(
        "R4", "Airport Express", "#ea580c",
        ["MKT", "CEN", "STD", "TEC", "AIR"],
        [2, 4, 4, 6],
    ),
]


def stop_coordinates(stop: SampleStop) -> tuple[float, float]:
    """Convert grid position to (lat, lon)."""
    lat0, lon0 = CITY_CENTER
    return (
        round(lat0 + stop.y * GRID_STEP_LAT, 6),
        round(lon0 + stop.x * GRID_STEP_LON, 6),
    )


def route_segments(route: SampleRoute) -> list[tuple[str, str, float]]:
    """Return (from, to, minutes) for every segment, in both directions."""
    stops = route.stop_ids
    expected = len(stops) if route.is_loop else len(stops) - 1
    if len(route.travel_times_min) != expected:
        raise ValueError(
            f"Route {route.id}: expected {expected} travel times, "
            f"got {len(route.travel_times_min)}"
        )

    segments: list[tuple[str, str, float]] = []
    for i, minutes in enumerate(route.travel_times_min):
        a, b = stops[i], stops[(i + 1) % len(stops)]
        segments.append((a, b, float(minutes)))
        segments.append((b, a, float(minutes)))
    return segments
