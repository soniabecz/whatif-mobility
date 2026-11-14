"""GTFS import (Day 14) on a tiny hand-made feed.

    Tram line 1:  A (posts A1, A2) -- B -- C      (B and C: one post each)
    Tram line 2:  C -- D
    Bus line 100: A -- D                          (left out when importing trams)
    "Far" posts: two posts named "Dworzec 01/02" 2 km apart -> two stations.
"""

import zipfile
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Connection, NetworkSource, Route, SavedScenario, Stop
from app.services.gtfs_import import (
    GtfsError,
    SourceInfo,
    choose_reference_date,
    import_feed,
    write_network,
)
from app.services.network_service import build_graph_from_db
from app.services.simulation_service import simulate
from app.schemas.scenario import Scenario

WED = date(2026, 11, 18)
TODAY = date(2026, 11, 13)  # a Friday


def _trip_rows(trip: str, calls: list[tuple[str, str]]) -> list[str]:
    return [f"{trip},{time},{time},{stop},{n}" for n, (stop, time) in enumerate(calls, start=1)]


def _feed(tmp_path: Path, **overrides: str | None) -> Path:
    files: dict[str, str | None] = {
        "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\n0,Test Transit,https://t.test,Europe/Warsaw\n",
        "feed_info.txt": "feed_publisher_name,feed_publisher_url,feed_lang\nTest Publisher,https://t.test,pl\n",
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\n"
                     "11,Alfa 01,54.3500,18.6000\n12,Alfa 02,54.3502,18.6004\n"
                     "20,Beta 01,54.3600,18.6000\n30,Gamma 01,54.3700,18.6000\n40,Delta,54.3800,18.6100\n"
                     "50,Dworzec 01,54.3000,18.5000\n51,Dworzec 02,54.3180,18.5000\n",
        "routes.txt": "route_id,agency_id,route_short_name,route_type,route_color\n"
                      "r1,0,1,900,ff0000\nr2,0,2,0,ff0000\nr100,0,100,3,0000ff\n",
        # Wednesdays only (service "wd"); a Saturday service that is never used.
        "calendar_dates.txt": "service_id,date,exception_type\nwd,20261118,1\nwd,20261125,1\nsat,20261114,1\n",
        "trips.txt": "route_id,service_id,trip_id,direction_id\n"
                     + "".join(f"r1,wd,t1-{i},0\n" for i in range(3))   # A -> B -> C, 3 trips in the peak
                     + "r1,wd,t1-short,0\n"                                # A -> B only (a short run)
                     + "r1,wd,t1-back,1\n"                                 # C -> B -> A
                     + "r2,wd,t2,0\nr2,wd,t2-late,0\n"                     # C -> D, outside the peak
                     + "r100,wd,b1,0\nr1,sat,t1-sat,0\n",
        "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n" + "\n".join(
            _trip_rows("t1-0", [("11", "07:00:00"), ("20", "07:02:00"), ("30", "07:05:00")])
            + _trip_rows("t1-1", [("12", "07:30:00"), ("20", "07:33:00"), ("30", "07:36:00")])
            + _trip_rows("t1-2", [("11", "08:00:00"), ("20", "08:02:00"), ("30", "08:06:00")])
            + _trip_rows("t1-short", [("11", "08:30:00"), ("20", "08:32:00")])
            + _trip_rows("t1-back", [("30", "09:30:00"), ("20", "09:33:00"), ("11", "09:35:00")])
            + _trip_rows("t2", [("30", "10:00:00"), ("40", "10:00:00")])  # 0 min in the timetable
            + _trip_rows("t2-late", [("30", "12:00:00"), ("40", "12:00:20")])
            + _trip_rows("b1", [("11", "07:10:00"), ("40", "07:20:00")])
            + _trip_rows("t1-sat", [("11", "10:00:00"), ("50", "10:30:00"), ("51", "10:40:00")])
        ) + "\n",
    }
    files.update(overrides)
    path = tmp_path / "feed.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            if content is not None:
                archive.writestr(zipfile.ZipInfo(name, date_time=(2026, 11, 13, 2, 46, 0)), content)
    return path


SOURCE = SourceInfo(attribution_url="https://t.test/open", licence="CC BY", feed_url="https://t.test/feed.zip",
                    downloaded=date(2026, 11, 13))


def _trams(tmp_path: Path, **overrides: str | None):  # type: ignore[no-untyped-def]
    return import_feed(_feed(tmp_path, **overrides), {"tram"}, TODAY, source=SOURCE)


def test_stations_lines_and_links(tmp_path: Path) -> None:
    network = _trams(tmp_path)
    stations = {s.name: s for s in network.stops}
    assert sorted(stations) == ["Alfa", "Beta", "Delta", "Gamma"]  # Dworzec: Saturday only
    alfa = stations["Alfa"]
    assert (alfa.id, alfa.post_ids, alfa.lat) == ("S11", ("11", "12"), 54.3501)  # average position
    assert [(r.id, r.name) for r in network.routes] == [("T1", "Tram 1"), ("T2", "Tram 2")]  # no bus
    links = {(l.route_id, l.from_stop_id, l.to_stop_id): l.travel_time_min for l in network.links}
    assert links == {
        ("T1", "S11", "S20"): 2.0,   # median of 2, 3, 2, 2 (the short run counts too)
        ("T1", "S20", "S30"): 3.0,   # median of 3, 3, 4
        ("T1", "S30", "S20"): 3.0,   # direction 1 has its own times
        ("T1", "S20", "S11"): 2.0,
        ("T2", "S30", "S40"): 0.5,   # 0 and 0.33 min in the timetable: at least 0.5
    }
    assert network.warnings == []  # the short run follows the main sequence


def test_headways_from_the_timetable(tmp_path: Path) -> None:
    routes = {r.id: r for r in _trams(tmp_path).routes}
    # T1: direction 0 has 4 departures 7:00-9:00 -> 30 min; direction 1 none in the peak.
    assert routes["T1"].headway_min == 30.0
    # T2: no peak trips: the average gap over the day, 10:00 and 12:00 -> 120.
    assert routes["T2"].headway_min == 120.0


def test_colours_are_distinct_when_the_feed_repeats_them(tmp_path: Path) -> None:
    routes = _trams(tmp_path).routes
    assert len({r.color for r in routes}) == 2 and all(r.color.startswith("#") for r in routes)


def test_posts_far_apart_stay_separate_stations(tmp_path: Path) -> None:
    network = import_feed(_feed(tmp_path), {"tram"}, TODAY, date(2026, 11, 14), SOURCE)
    names = {s.name: s.id for s in network.stops}
    assert names["Dworzec"] == "S50" and names["Dworzec (2)"] == "S51"


def test_buses_and_all_modes(tmp_path: Path) -> None:
    buses = import_feed(_feed(tmp_path), {"bus"}, TODAY, source=SOURCE)
    assert [r.id for r in buses.routes] == ["B100"]
    both = import_feed(_feed(tmp_path), {"tram", "bus"}, TODAY, source=SOURCE)
    assert [r.id for r in both.routes] == ["B100", "T1", "T2"]


def test_branches_left_out_are_reported(tmp_path: Path) -> None:
    trips = ("route_id,service_id,trip_id,direction_id\n" + "".join(f"r1,wd,t1-{i},0\n" for i in range(3))
             + "r1,wd,t1-branch,0\n")
    stop_times = ("trip_id,arrival_time,departure_time,stop_id,stop_sequence\n" + "\n".join(
        _trip_rows("t1-0", [("11", "07:00:00"), ("20", "07:02:00")])
        + _trip_rows("t1-1", [("11", "07:20:00"), ("20", "07:22:00")])
        + _trip_rows("t1-2", [("11", "07:40:00"), ("20", "07:42:00")])
        + _trip_rows("t1-branch", [("11", "08:00:00"), ("40", "08:05:00")])) + "\n")
    network = _trams(tmp_path, **{"trips.txt": trips, "stop_times.txt": stop_times})
    assert ("T1", "S11", "S40") not in {(l.route_id, l.from_stop_id, l.to_stop_id) for l in network.links}
    assert network.warnings == ["T1 direction 0: 1 of 4 trips run links outside the main sequence "
                                "(those links are left out)"]


def test_source_and_attribution(tmp_path: Path) -> None:
    source = _trams(tmp_path).source
    assert (source.publisher, source.name) == ("Test Publisher", "Test Publisher – trams")
    assert (source.feed_created, source.downloaded, source.reference_date) == ("2026-11-13", "2026-11-13", "2026-11-18")
    assert (source.attribution_url, source.licence) == ("https://t.test/open", "CC BY")
    assert "most frequent station sequence" in source.method and "2026-11-18" in source.method


def test_reference_date() -> None:
    days = {date(2026, 11, 14): {"s"}, date(2026, 11, 18): {"w"}, date(2026, 11, 25): {"w"}}
    assert choose_reference_date(days, TODAY, None) == WED  # the first Wednesday from today
    assert choose_reference_date({date(2026, 11, 14): {"s"}}, TODAY, None) == date(2026, 11, 14)
    assert choose_reference_date(days, TODAY, date(2026, 11, 25)) == date(2026, 11, 25)
    with pytest.raises(GtfsError, match="no service on 2026-11-19"):
        choose_reference_date(days, TODAY, date(2026, 11, 19))
    with pytest.raises(GtfsError, match="no service from 2026-12-01 on"):
        choose_reference_date(days, date(2026, 12, 1), None)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"stops.txt": None}, "the feed has no stops.txt"),
        ({"stops.txt": "stop_id,stop_name\n11,Alfa\n"}, "stops.txt has no column stop_lat, stop_lon"),
        ({"calendar_dates.txt": None}, "neither calendar.txt nor calendar_dates.txt"),
        ({"routes.txt": "route_id,route_type\nr9,4\n"}, "no tram routes"),
        ({"stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\nt1-0,7am,7am,11,1\n"},
         "invalid time '7am'"),
    ],
)
def test_malformed_feeds_are_refused(tmp_path: Path, overrides: dict[str, str | None], message: str) -> None:
    with pytest.raises(GtfsError, match=message):
        _trams(tmp_path, **overrides)


def test_not_a_zip(tmp_path: Path) -> None:
    bad = tmp_path / "feed.zip"
    bad.write_text("not a zip")
    with pytest.raises(GtfsError, match="not a readable zip file"):
        import_feed(bad, {"tram"}, TODAY)


def test_write_replaces_the_network_and_keeps_saved_scenarios(tmp_path: Path, db: Session) -> None:
    db.add(SavedScenario(name="Sample plan", changes_json='[{"type": "close_stop", "stop_id": "CEN"}]'))
    db.commit()
    write_network(db, _trams(tmp_path))
    assert sorted(db.scalars(select(Stop.name))) == ["Alfa", "Beta", "Delta", "Gamma"]
    assert sorted(db.scalars(select(Route.id))) == ["T1", "T2"]
    assert db.query(Connection).count() == 5
    assert all(stop.activity == 1 for stop in db.scalars(select(Stop)))  # no demand data
    assert db.scalars(select(NetworkSource.publisher)).one() == "Test Publisher"
    assert db.scalars(select(SavedScenario.name)).all() == ["Sample plan"]  # kept; flagged as not fitting


def test_the_imported_network_simulates(tmp_path: Path, db: Session) -> None:
    write_network(db, _trams(tmp_path))
    graph = build_graph_from_db(db)
    result = simulate(graph, Scenario.model_validate({"changes": [{"type": "close_stop", "stop_id": "S20"}]}))
    assert result.summary.total_journeys == 12  # 4 stations
    assert result.summary.to_or_from_closed_stop == 6


def test_api_shows_the_source(tmp_path: Path, client, db: Session) -> None:  # type: ignore[no-untyped-def]
    write_network(db, _trams(tmp_path))
    source = client.get("/api/network").json()["source"]
    assert source["publisher"] == "Test Publisher" and source["reference_date"] == "2026-11-18"


def test_calls_without_boarding_or_alighting_are_driven_through(tmp_path: Path) -> None:
    stops = ("stop_id,stop_name,stop_lat,stop_lon\n11,Alfa 01,54.35,18.60\n20,Beta 01,54.36,18.60\n"
             "90,Zajezdnia T2,54.355,18.60\n")
    trips = "route_id,service_id,trip_id,direction_id\nr1,wd,t1,0\n"
    stop_times = ("trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type\n"
                  "t1,07:00:00,07:00:00,11,1,0,0\n"
                  "t1,07:02:00,07:02:00,90,2,1,1\n"      # depot gate: no boarding, no alighting
                  "t1,07:05:00,07:05:00,20,3,0,0\n")
    network = _trams(tmp_path, **{"stops.txt": stops, "trips.txt": trips, "stop_times.txt": stop_times})
    assert sorted(s.name for s in network.stops) == ["Alfa", "Beta"]
    assert [(l.from_stop_id, l.to_stop_id, l.travel_time_min) for l in network.links] == [("S11", "S20", 5.0)]
    assert "driven through" in network.source.method


def test_the_source_names_the_modes(tmp_path: Path) -> None:
    both = import_feed(_feed(tmp_path), {"tram", "bus"}, TODAY, source=SOURCE)
    assert both.source.name.endswith("trams and buses")
