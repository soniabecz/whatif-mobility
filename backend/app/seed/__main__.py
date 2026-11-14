"""Create the tables and load the invented sample network: TEST DATA ONLY.

The app runs on Gdańsk (python -m app.import_gtfs). The sample city is what the
tests run on; this command seeds it only into a test database (a file named
e2e-*.db), never into the app's database.

Usage (from backend/, with .venv active):
    WHATIF_DATABASE=e2e-sample.db python -m app.seed             # reset to the sample
    WHATIF_DATABASE=e2e-sample.db python -m app.seed --if-empty  # only a fresh one

If the NETWORK tables are outdated (columns differ from the models, e.g. after
a new field was added), they are dropped and rebuilt in both modes: they only
hold generated sample data. Saved scenarios are user data and are never
dropped: if their table is outdated, the command stops and says so.
"""

import argparse

from sqlalchemy import func, select

from app.database import DATABASE_URL, TEST_DATABASE_PREFIX, SessionLocal, database_file, engine
from app.models import Connection, Route, Stop
from app.seed.seed_db import network_is_empty, prepare_tables, sample_lacks_patterns, seed_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the sample bus network.")
    parser.add_argument(
        "--if-empty",
        action="store_true",
        help="do nothing when the database already holds a network",
    )
    args = parser.parse_args()

    target = database_file().name
    if not target.startswith(TEST_DATABASE_PREFIX):
        raise SystemExit(
            f"The sample city is test data and is not written into {target}: the app runs on "
            f"Gdańsk (python -m app.import_gtfs). For the browser tests use a test database, "
            f"e.g. WHATIF_DATABASE={TEST_DATABASE_PREFIX}sample.db python -m app.seed"
        )

    prepare_tables(engine)
    with SessionLocal() as db:
        if args.if_empty and not network_is_empty(db):
            if not sample_lacks_patterns(db):
                print(f"Database already seeded, left unchanged: {DATABASE_URL}")
                return
            print("The sample network has no route patterns yet (Day 14 part 4): reseeding it.")
        seed_database(db)
        counts = {
            name: db.scalar(select(func.count()).select_from(model))
            for name, model in (("stops", Stop), ("routes", Route), ("connections", Connection))
        }
    print(f"Seeded {DATABASE_URL}: {counts}")


if __name__ == "__main__":
    main()
