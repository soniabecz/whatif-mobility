"""Build the network from a real GTFS timetable feed (Day 14).

The app's model is simpler than a timetable, so the import makes documented
choices (also stored in ``network_source.method`` and shown in the app):

- Calls where passengers can neither board nor alight (pickup_type and
  drop_off_type both 1: depot gates, timing points) are driven through: they
  are not stations, and the link runs from the previous to the next real stop.
- Stations: stop posts are grouped by name without the post number
  ("Wrzeszcz PKP 05" + "Wrzeszcz PKP 06" -> "Wrzeszcz PKP"); posts with the
  same name more than ``MAX_POST_DISTANCE_M`` apart stay separate stations.
  A station sits at the average position of its posts.
- One reference weekday: only its trips are used.
- Lines: per route and direction, the most frequent sequence of stations on
  that day; branches that only some trips run are left out.
- Travel time of a link: the median scheduled time over all that day's trips of
  the route that run it directly (at least ``MIN_LINK_MIN``: timetables are
  rounded to the minute, and a link cannot take no time).
- Headway: from trips per direction starting in the 7-9 morning peak
  (120 min / trips), averaged over directions; lines without peak trips use the
  average gap over the day. Clamped to the app's 1-120 min.
- Demand: GTFS has no passenger data, so every station gets the same level
  (demand-weighted figures then equal the plain ones).

No timetable value is invented: every time and headway comes from the feed.
"""

import csv
import io
import math
import re
import statistics
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Connection, NetworkSource, Route, Stop
from app.schemas.scenario import MAX_HEADWAY_MIN, MIN_HEADWAY_MIN

MAX_POST_DISTANCE_M = 500.0
MIN_LINK_MIN = 0.5
PEAK_START_MIN, PEAK_END_MIN = 7 * 60, 9 * 60

# GTFS route types (basic and extended) per mode.
MODE_ROUTE_TYPES: dict[str, set[int]] = {
    "tram": {0, *range(900, 907)},
    "bus": {3, 11, *range(700, 717), 800},
}
MODE_LABELS = {"tram": "Tram", "bus": "Bus"}
MODE_PREFIX = {"tram": "T", "bus": "B"}

# Distinct line colours, used when the feed's own colours are missing or repeat.
# Chosen to stay apart from each other and from the new-route colours.
LINE_COLORS = (
    "#dc2626", "#2563eb", "#16a34a", "#ea580c", "#0891b2", "#c026d3",
    "#111827", "#a16207", "#ec4899", "#115e59", "#6d28d9", "#4d7c0f",
)


class GtfsError(ValueError):
    """The feed cannot be imported (missing file or column, no service, ...)."""


# --- Result ----------------------------------------------------------------------------

@dataclass(frozen=True)
class ImportedStop:
    id: str
    name: str
    lat: float
    lon: float
    post_ids: tuple[str, ...]


@dataclass(frozen=True)
class ImportedRoute:
    id: str
    name: str
    color: str
    headway_min: float
    gtfs_route_id: str


@dataclass(frozen=True)
class ImportedLink:
    route_id: str
    from_stop_id: str
    to_stop_id: str
    travel_time_min: float


@dataclass(frozen=True)
class SourceInfo:
    """Attribution details the data's terms require (shown in the app)."""

    publisher: str = ""  # empty: taken from the feed (feed_info, else agency)
    attribution_url: str = ""
    licence: str = ""
    feed_url: str = ""
    downloaded: date | None = None


@dataclass
class ImportedNetwork:
    stops: list[ImportedStop]
    routes: list[ImportedRoute]
    links: list[ImportedLink]
    source: NetworkSource
    warnings: list[str] = field(default_factory=list)


# --- Reading the feed ----------------------------------------------------------------------

class Feed:
    """Lazy access to the CSV tables of a GTFS zip."""

    def __init__(self, path: Path) -> None:
        try:
            self._zip = zipfile.ZipFile(path)
        except (OSError, zipfile.BadZipFile) as error:
            raise GtfsError(f"{path} is not a readable zip file: {error}") from error
        self._names = {Path(name).name: name for name in self._zip.namelist()}

    def has(self, table: str) -> bool:
        return f"{table}.txt" in self._names

    def rows(self, table: str, required: tuple[str, ...] = ()) -> Iterator[dict[str, str]]:
        name = self._names.get(f"{table}.txt")
        if name is None:
            raise GtfsError(f"the feed has no {table}.txt")
        with self._zip.open(name) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            missing = [column for column in required if column not in (reader.fieldnames or [])]
            if missing:
                raise GtfsError(f"{table}.txt has no column {', '.join(missing)}")
            for row in reader:
                yield {key: (value or "").strip() for key, value in row.items() if key}

    def created(self) -> date:
        """Date of the feed's newest file (the data's creation date)."""
        stamps = [info.date_time for info in self._zip.infolist() if not info.is_dir()]
        return datetime(*max(stamps)).date()  # type: ignore[misc]


def _minutes(value: str) -> float:
    """GTFS time (HH:MM:SS, hours may exceed 24) in minutes after midnight."""
    try:
        hours, minutes, seconds = (int(part) for part in value.split(":"))
    except ValueError as error:
        raise GtfsError(f"invalid time {value!r} in stop_times.txt") from error
    return hours * 60 + minutes + seconds / 60


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rad = math.radians
    h = (math.sin(rad(lat2 - lat1) / 2) ** 2
         + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(rad(lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def _sort_key(value: str) -> tuple[int, int | str]:
    """Numeric ids in numeric order, others after them."""
    return (0, int(value)) if value.isdigit() else (1, value)


# --- Service days ------------------------------------------------------------------------

def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as error:
        raise GtfsError(f"invalid date {value!r}") from error


def active_services(feed: Feed) -> dict[date, set[str]]:
    """Service ids running on each date (calendar.txt and calendar_dates.txt)."""
    days: dict[date, set[str]] = defaultdict(set)
    weekdays = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    if feed.has("calendar"):
        for row in feed.rows("calendar", ("service_id", "start_date", "end_date", *weekdays)):
            day, end = _parse_date(row["start_date"]), _parse_date(row["end_date"])
            while day <= end:
                if row[weekdays[day.weekday()]] == "1":
                    days[day].add(row["service_id"])
                day += timedelta(days=1)
    if feed.has("calendar_dates"):
        for row in feed.rows("calendar_dates", ("service_id", "date", "exception_type")):
            day = _parse_date(row["date"])
            if row["exception_type"] == "1":
                days[day].add(row["service_id"])
            elif row["exception_type"] == "2":
                days[day].discard(row["service_id"])
    if not feed.has("calendar") and not feed.has("calendar_dates"):
        raise GtfsError("the feed has neither calendar.txt nor calendar_dates.txt")
    return {day: services for day, services in days.items() if services}


def choose_reference_date(days: dict[date, set[str]], today: date, requested: date | None) -> date:
    """The requested date, else the first Wednesday from today with service,
    else the first day from today with service."""
    if requested is not None:
        if requested not in days:
            raise GtfsError(f"the feed has no service on {requested.isoformat()}")
        return requested
    upcoming = sorted(day for day in days if day >= today)
    if not upcoming:
        raise GtfsError(f"the feed has no service from {today.isoformat()} on (is it outdated?)")
    wednesdays = [day for day in upcoming if day.weekday() == 2]
    return wednesdays[0] if wednesdays else upcoming[0]


# --- Stations -----------------------------------------------------------------------------

def group_stations(posts: dict[str, dict[str, str]]) -> tuple[list[ImportedStop], dict[str, str]]:
    """Group stop posts into stations; returns (stations, post id -> station id)."""
    by_name: dict[str, list[str]] = defaultdict(list)
    for post_id, post in posts.items():
        by_name[re.sub(r"\s+\d{1,2}$", "", post["stop_name"]).strip()].append(post_id)

    clusters: list[tuple[str, list[str]]] = []
    for name in sorted(by_name):
        groups: list[list[str]] = []
        for post_id in sorted(by_name[name], key=_sort_key):
            lat, lon = float(posts[post_id]["stop_lat"]), float(posts[post_id]["stop_lon"])
            for group in groups:
                first = posts[group[0]]
                if _distance_m(lat, lon, float(first["stop_lat"]), float(first["stop_lon"])) <= MAX_POST_DISTANCE_M:
                    group.append(post_id)
                    break
            else:
                groups.append([post_id])
        for number, group in enumerate(groups, start=1):
            clusters.append((name if number == 1 else f"{name} ({number})", group))

    stations: list[ImportedStop] = []
    station_of: dict[str, str] = {}
    used_ids: set[str] = set()
    for index, (name, group) in enumerate(clusters, start=1):
        first = min(group, key=_sort_key)
        # "S" + the first post's id: stable across imports, and letters+digits
        # like the app's other ids. Fallback for long or unusual post ids.
        station_id = f"S{first}" if re.fullmatch(r"[A-Za-z0-9]{1,9}", first) else f"S{index}"
        while station_id in used_ids:
            station_id = f"S{index}x"
        used_ids.add(station_id)
        stations.append(ImportedStop(
            id=station_id,
            name=name[:100],
            lat=round(statistics.fmean(float(posts[p]["stop_lat"]) for p in group), 6),
            lon=round(statistics.fmean(float(posts[p]["stop_lon"]) for p in group), 6),
            post_ids=tuple(sorted(group, key=_sort_key)),
        ))
        for post_id in group:
            station_of[post_id] = station_id
    return stations, station_of


# --- Lines ---------------------------------------------------------------------------------

def _mode_of(route_type: str) -> str | None:
    try:
        number = int(route_type)
    except ValueError:
        return None
    return next((mode for mode, types in MODE_ROUTE_TYPES.items() if number in types), None)


def _route_ids(routes: dict[str, dict[str, str]], modes: dict[str, str]) -> dict[str, str]:
    """GTFS route id -> app route id: mode letter + line number (T10, B100), unique."""
    result: dict[str, str] = {}
    used: set[str] = set()
    for gtfs_id in sorted(routes, key=lambda r: (modes[r], _sort_key(routes[r].get("route_short_name") or r))):
        short = re.sub(r"[^A-Za-z0-9]", "", routes[gtfs_id].get("route_short_name") or gtfs_id)
        candidate = f"{MODE_PREFIX[modes[gtfs_id]]}{short}"[:10] or f"{MODE_PREFIX[modes[gtfs_id]]}{len(used)}"
        number = 2
        while candidate in used:
            candidate = f"{MODE_PREFIX[modes[gtfs_id]]}{short}"[:8] + f"_{number}"
            number += 1
        used.add(candidate)
        result[gtfs_id] = candidate
    return result


def _colors(routes: dict[str, dict[str, str]], order: list[str]) -> dict[str, str]:
    """The feed's colours when every line has its own, else distinct ones from LINE_COLORS."""
    own = {r: routes[r].get("route_color", "").lower() for r in order}
    valid = all(re.fullmatch(r"[0-9a-f]{6}", color) for color in own.values())
    if valid and len(set(own.values())) == len(own):
        return {r: f"#{color}" for r, color in own.items()}
    return {r: LINE_COLORS[i % len(LINE_COLORS)] for i, r in enumerate(order)}


def _headway(departures: dict[str, list[float]]) -> float:
    """Minutes between buses from the first departures of each direction's trips."""
    peak = [
        sum(PEAK_START_MIN <= t < PEAK_END_MIN for t in times) for times in departures.values()
    ]
    if any(peak):
        value = statistics.fmean((PEAK_END_MIN - PEAK_START_MIN) / n for n in peak if n)
    else:
        gaps = [
            (max(times) - min(times)) / (len(times) - 1)
            for times in departures.values() if len(times) >= 2
        ]
        value = statistics.fmean(gaps) if gaps else MAX_HEADWAY_MIN
    return round(min(MAX_HEADWAY_MIN, max(MIN_HEADWAY_MIN, value)), 1)


# --- The import --------------------------------------------------------------------------------

METHOD = (
    "Stop posts grouped into stations by name (posts over {distance:g} m apart stay separate); "
    "calls without boarding or alighting (depot gates, timing points) are driven through. "
    "Lines: each route's most frequent station sequence per direction on {day}. "
    "Link times: median scheduled time on that day (at least {floor:g} min). "
    "Headways: trips per direction starting 7:00-9:00 on that day (otherwise the average gap). "
    "No demand data: every station weighs the same."
)


def import_feed(
    path: Path,
    modes: set[str],
    today: date,
    reference_date: date | None = None,
    source: SourceInfo = SourceInfo(),
) -> ImportedNetwork:
    """Build the network for ``modes`` ("tram", "bus") from the GTFS zip at ``path``."""
    unknown_modes = modes - set(MODE_ROUTE_TYPES)
    if not modes or unknown_modes:
        raise GtfsError(f"modes must be among {', '.join(sorted(MODE_ROUTE_TYPES))}")
    feed = Feed(path)

    days = active_services(feed)
    day = choose_reference_date(days, today, reference_date)
    services = days[day]

    all_routes = {r["route_id"]: r for r in feed.rows("routes", ("route_id", "route_type"))}
    route_modes = {r: m for r, row in all_routes.items() if (m := _mode_of(row["route_type"])) in modes}
    if not route_modes:
        raise GtfsError(f"the feed has no {' or '.join(sorted(modes))} routes")

    trips = {
        row["trip_id"]: row
        for row in feed.rows("trips", ("route_id", "service_id", "trip_id"))
        if row["route_id"] in route_modes and row["service_id"] in services
    }
    if not trips:
        raise GtfsError(f"no {' or '.join(sorted(modes))} trips run on {day.isoformat()}")

    calls: dict[str, list[tuple[int, str, float, float]]] = defaultdict(list)
    for row in feed.rows("stop_times", ("trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time")):
        if row["trip_id"] in trips and not (row.get("pickup_type") == "1" and row.get("drop_off_type") == "1"):
            arrival = _minutes(row["arrival_time"] or row["departure_time"])
            departure = _minutes(row["departure_time"] or row["arrival_time"])
            calls[row["trip_id"]].append((int(row["stop_sequence"]), row["stop_id"], arrival, departure))

    used_posts = {stop_id for trip_calls in calls.values() for _, stop_id, _, _ in trip_calls}
    posts = {
        row["stop_id"]: row
        for row in feed.rows("stops", ("stop_id", "stop_name", "stop_lat", "stop_lon"))
        if row["stop_id"] in used_posts
    }
    missing = used_posts - set(posts)
    if missing:
        raise GtfsError(f"stop_times.txt uses stops missing from stops.txt: {', '.join(sorted(missing)[:5])}")
    stations, station_of = group_stations(posts)

    # Each trip as stations in order: (station, arrival, departure); a run of
    # posts of one station becomes one call.
    sequences: dict[str, list[tuple[str, float, float]]] = {}
    for trip_id, trip_calls in calls.items():
        merged: list[tuple[str, float, float]] = []
        for _, post_id, arrival, departure in sorted(trip_calls):
            station = station_of[post_id]
            if merged and merged[-1][0] == station:
                merged[-1] = (station, merged[-1][1], departure)
            else:
                merged.append((station, arrival, departure))
        if len(merged) >= 2:
            sequences[trip_id] = merged

    # Per route: the most frequent station sequence per direction; link times
    # from every trip of the route that runs the link directly.
    patterns: dict[tuple[str, str], Counter[tuple[str, ...]]] = defaultdict(Counter)
    link_times: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    first_departures: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for trip_id, sequence in sequences.items():
        trip = trips[trip_id]
        route, direction = trip["route_id"], trip.get("direction_id", "")
        patterns[(route, direction)][tuple(station for station, _, _ in sequence)] += 1
        first_departures[route][direction].append(sequence[0][2])
        for (a, _, departs), (b, arrives, _) in zip(sequence, sequence[1:]):
            link_times[(route, a, b)].append(arrives - departs)

    gtfs_routes = sorted(
        {route for route, _ in patterns},
        key=lambda r: (route_modes[r], _sort_key(all_routes[r].get("route_short_name") or r)),
    )
    app_ids = _route_ids({r: all_routes[r] for r in gtfs_routes}, route_modes)
    colors = _colors(all_routes, gtfs_routes)

    links: dict[tuple[str, str, str], ImportedLink] = {}
    warnings: list[str] = []
    for (route, direction), counter in sorted(patterns.items()):
        # Most trips first; ties: the longer sequence, then a fixed order.
        main = min(counter, key=lambda seq: (-counter[seq], -len(seq), seq))
        for a, b in zip(main, main[1:]):
            minutes = max(MIN_LINK_MIN, round(statistics.median(link_times[(route, a, b)]), 1))
            links.setdefault((app_ids[route], a, b), ImportedLink(app_ids[route], a, b, minutes))
        # Short runs (a stretch of the main sequence, e.g. to the depot) are
        # covered; only trips that leave the main sequence lose something.
        main_links = set(zip(main, main[1:]))
        off_route = sum(
            n for seq, n in counter.items() if not set(zip(seq, seq[1:])) <= main_links
        )
        if off_route:
            warnings.append(
                f"{app_ids[route]} direction {direction or '-'}: {off_route} of {counter.total()} trips "
                "run links outside the main sequence (those links are left out)"
            )

    imported_routes = [
        ImportedRoute(
            id=app_ids[r],
            name=f"{MODE_LABELS[route_modes[r]]} {all_routes[r].get('route_short_name') or r}"[:100],
            color=colors[r],
            headway_min=_headway(first_departures[r]),
            gtfs_route_id=r,
        )
        for r in gtfs_routes
    ]
    used_stations = {link.from_stop_id for link in links.values()} | {link.to_stop_id for link in links.values()}

    publisher = source.publisher
    if not publisher and feed.has("feed_info"):
        publisher = next((row.get("feed_publisher_name", "") for row in feed.rows("feed_info")), "")
    if not publisher and feed.has("agency"):
        publisher = next((row.get("agency_name", "") for row in feed.rows("agency")), "")
    mode_names = " and ".join(f"{MODE_LABELS[m].lower()}s" for m in sorted(modes, reverse=True))
    network_source = NetworkSource(
        name=f"{publisher or 'GTFS feed'} – {mode_names}"[:200],
        publisher=publisher or "unknown publisher",
        attribution_url=source.attribution_url,
        licence=source.licence,
        feed_url=source.feed_url or path.name,
        feed_created=feed.created().isoformat(),
        downloaded=(source.downloaded or today).isoformat(),
        reference_date=day.isoformat(),
        method=METHOD.format(distance=MAX_POST_DISTANCE_M, day=day.isoformat(), floor=MIN_LINK_MIN),
    )
    return ImportedNetwork(
        stops=[station for station in stations if station.id in used_stations],
        routes=imported_routes,
        links=sorted(links.values(), key=lambda l: (l.route_id, l.from_stop_id, l.to_stop_id)),
        source=network_source,
        warnings=warnings,
    )


def write_network(db: Session, network: ImportedNetwork) -> None:
    """Replace the network tables with the imported network (one transaction).
    Saved scenarios are kept; those that no longer fit are flagged when listed."""
    try:
        db.execute(delete(Connection))
        db.execute(delete(Route))
        db.execute(delete(Stop))
        db.execute(delete(NetworkSource))
        for stop in network.stops:
            db.add(Stop(id=stop.id, name=stop.name, lat=stop.lat, lon=stop.lon, activity=1))
        for route in network.routes:
            db.add(Route(id=route.id, name=route.name, color=route.color, headway_min=route.headway_min))
        db.flush()
        for link in network.links:
            db.add(Connection(
                route_id=link.route_id,
                from_stop_id=link.from_stop_id,
                to_stop_id=link.to_stop_id,
                travel_time_min=link.travel_time_min,
            ))
        db.add(network.source)
        db.commit()
    except Exception:
        db.rollback()
        raise
