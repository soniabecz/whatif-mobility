"""Create the tables and load the sample network.

Usage (from backend/, with .venv active):
    python -m app.seed              # always reset to the sample network
    python -m app.seed --if-empty   # only seed a fresh database (used by dev.sh);
                                    # also a sample seeded before routes had patterns

If the NETWORK tables are outdated (columns differ from the models, e.g. after
a new field was added), they are dropped and rebuilt in both modes: they only
hold generated sample data. Saved scenarios are user data and are never
dropped: if their table is outdated, the command stops and says so.
"""

import argparse

from sqlalchemy import func, select

from app.database import DATABASE_URL, SessionLocal, engine
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
