"""Create the tables and load the sample network.

Usage (from backend/, with .venv active):
    python -m app.seed              # always reset to the sample network
    python -m app.seed --if-empty   # only seed a fresh database (used by dev.sh)

If the NETWORK tables are outdated (columns differ from the models, e.g. after
a new field was added), they are dropped and rebuilt in both modes: they only
hold generated sample data. Saved scenarios are user data and are never
dropped: if their table is outdated, the command stops and says so.
"""

import argparse
import sys

from sqlalchemy import func, select

from app.database import DATABASE_URL, Base, SessionLocal, engine
from app.models import NETWORK_TABLES, Connection, Route, Stop
from app.seed.seed_db import network_is_empty, outdated_tables, seed_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the sample bus network.")
    parser.add_argument(
        "--if-empty",
        action="store_true",
        help="do nothing when the database already holds a network",
    )
    args = parser.parse_args()

    outdated = outdated_tables(engine)
    user_tables = [name for name in outdated if name not in NETWORK_TABLES]
    if user_tables:
        sys.exit(
            f"Tables with saved user data are outdated ({', '.join(user_tables)}). "
            "They are not dropped automatically: back up backend/whatif.db, then update "
            "or delete those tables by hand."
        )
    if outdated:
        print(f"Network tables are outdated ({', '.join(outdated)}): rebuilding them from the models.")
        network = [Base.metadata.tables[name] for name in NETWORK_TABLES]
        Base.metadata.drop_all(engine, tables=network)
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
