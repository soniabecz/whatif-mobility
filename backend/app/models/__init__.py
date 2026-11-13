"""SQLAlchemy models. Importing this package registers all tables on Base."""

from app.models.network import Connection, Route, Stop
from app.models.scenario import SavedScenario

__all__ = ["Connection", "Route", "SavedScenario", "Stop"]

# Tables holding only generated sample data: safe to drop and rebuild.
NETWORK_TABLES = ("stops", "routes", "connections")
