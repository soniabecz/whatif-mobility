"""Create the tables and load the sample network.

Usage (from backend/, with .venv active):
    python -m app.seed
"""

from sqlalchemy import func, select

from app.database import DATABASE_URL, Base, SessionLocal, engine
from app.models import Connection, Route, Stop
from app.seed.seed_db import seed_database


def main() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_database(db)
        counts = {
            name: db.scalar(select(func.count()).select_from(model))
            for name, model in (("stops", Stop), ("routes", Route), ("connections", Connection))
        }
    print(f"Seeded {DATABASE_URL}: {counts}")


if __name__ == "__main__":
    main()
