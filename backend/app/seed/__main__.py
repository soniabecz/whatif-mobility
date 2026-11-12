"""Create the tables and load the sample network.

Usage (from backend/, with .venv active):
    python -m app.seed              # always reset to the sample network
    python -m app.seed --if-empty   # only seed a fresh database (used by dev.sh)

If the tables are outdated (columns differ from the models, e.g. after a
new field was added), they are dropped and rebuilt in both modes. That is
safe because the database only holds generated sample data.
"""

import argparse

from sqlalchemy import func, select

from app.database import DATABASE_URL, Base, SessionLocal, engine
from app.models import Connection, Route, Stop
from app.seed.seed_db import network_is_empty, schema_is_current, seed_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the sample bus network.")
    parser.add_argument(
        "--if-empty",
        action="store_true",
        help="do nothing when the database already holds a network",
    )
    args = parser.parse_args()

    if not schema_is_current(engine):
        print("Database tables are outdated: rebuilding them from the models.")
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if args.if_empty and not network_is_empty(db):
            print(f"Database already seeded, left unchanged: {DATABASE_URL}")
            return
        seed_database(db)
        counts = {
            name: db.scalar(select(func.count()).select_from(model))
            for name, model in (("stops", Stop), ("routes", Route), ("connections", Connection))
        }
    print(f"Seeded {DATABASE_URL}: {counts}")


if __name__ == "__main__":
    main()
