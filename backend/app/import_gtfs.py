"""Import a real network from a GTFS timetable feed (Day 14).

Usage (from backend/, with .venv active):
    python -m app.import_gtfs                 # Gdańsk trams and buses into gdansk.db
    python -m app.import_gtfs --if-empty      # only when no network is imported yet (dev.sh)
    python -m app.import_gtfs path/to/feed.zip --modes bus --date 2026-11-18 \\
        --attribution-url https://... --licence "..."

Then start the app: ./dev.sh (WHATIF_DATABASE picks another database file).

A URL is downloaded to backend/data/gtfs/ (git-ignored). The network tables of
the database are replaced; saved scenarios are kept. The data's terms require
naming the publisher and the creation and download dates; the app shows them.
Keeping the data current is the user's job: re-run this command now and then.
"""

import argparse
import sys
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from app.database import BACKEND_DIR, DATABASE_URL, SessionLocal, engine
from app.seed.seed_db import network_is_empty, prepare_tables
from app.services.network_service import get_source
from app.services.gtfs_import import GtfsError, SourceInfo, import_feed, write_network

# ZTM Gdańsk (https://ckan.multimediagdansk.pl/dataset/tristar). Terms: name the
# publisher and http://www.ztm.gda.pl/otwarty_ztm, and the creation and download dates.
GDANSK_FEED_URL = (
    "https://ckan.multimediagdansk.pl/dataset/c24aa637-3619-4dc2-a171-a23eec8f2172/"
    "resource/30e783e4-2bec-4a7d-bb22-ee3e3b26ca96/download/gtfsgoogle.zip"
)
GDANSK_ATTRIBUTION_URL = "http://www.ztm.gda.pl/otwarty_ztm"
GDANSK_LICENCE = "Creative Commons Attribution; terms of use of “Otwarte dane ZTM w Gdańsku”"
CACHE_DIR = BACKEND_DIR / "data" / "gtfs"
_MODES = {"tram": {"tram"}, "bus": {"bus"}, "all": {"tram", "bus"}}


def _download(url: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = CACHE_DIR / (Path(urlparse(url).path).name or "feed.zip")
    print(f"Downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "whatif-mobility-gtfs-import"})
    with urllib.request.urlopen(request, timeout=120) as response, open(target, "wb") as out:
        out.write(response.read())
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a network from a GTFS feed.")
    parser.add_argument("source", nargs="?", default=GDANSK_FEED_URL, help="zip file or URL (default: ZTM Gdańsk)")
    parser.add_argument("--modes", choices=sorted(_MODES), default="all", help="default: all (trams and buses)")
    parser.add_argument("--if-empty", action="store_true", help="do nothing when a network is already imported")
    parser.add_argument("--date", type=date.fromisoformat, help="reference weekday (default: next Wednesday)")
    parser.add_argument("--attribution-url", help="source link the data's terms ask for")
    parser.add_argument("--licence", help="licence and terms of the data")
    args = parser.parse_args()

    if args.if_empty:
        prepare_tables(engine)
        with SessionLocal() as db:
            if not network_is_empty(db):
                if get_source(db) is None:
                    sys.exit(
                        f"{DATABASE_URL} holds the invented sample city, but the app runs on Gdańsk only. "
                        "Use another database file (WHATIF_DATABASE) or delete this one."
                    )
                print(f"Network already imported, left unchanged: {DATABASE_URL}")
                return
        print("No network yet: importing Gdańsk (about 25 MB download, once).")

    is_url = args.source.startswith(("http://", "https://"))
    gdansk = args.source == GDANSK_FEED_URL
    try:
        path = _download(args.source) if is_url else Path(args.source)
    except OSError as error:
        sys.exit(f"Download failed: {error}")
    downloaded = date.today() if is_url else date.fromtimestamp(path.stat().st_mtime)
    source = SourceInfo(
        attribution_url=args.attribution_url or (GDANSK_ATTRIBUTION_URL if gdansk else ""),
        licence=args.licence or (GDANSK_LICENCE if gdansk else ""),
        feed_url=args.source,
        downloaded=downloaded,
    )
    if not source.attribution_url or not source.licence:
        print("Note: give --attribution-url and --licence so the app can credit the data.")

    try:
        network = import_feed(path, _MODES[args.modes], date.today(), args.date, source)
    except GtfsError as error:
        sys.exit(f"Import failed: {error}")

    prepare_tables(engine)
    with SessionLocal() as db:
        write_network(db, network)
    print(f"Imported into {DATABASE_URL}: {len(network.stops)} stations, {len(network.routes)} lines, "
          f"{len(network.links)} links (reference day {network.source.reference_date}).")
    for warning in network.warnings:
        print(f"  note: {warning}")


if __name__ == "__main__":
    main()
