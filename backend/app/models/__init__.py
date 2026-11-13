"""SQLAlchemy models. Importing this package registers all tables on Base."""

from app.models.network import Connection, NetworkSource, Route, Stop
from app.models.scenario import SavedScenario

__all__ = ["Connection", "NetworkSource", "Route", "SavedScenario", "Stop"]

# Tables holding only generated network data (sample or imported): safe to
# drop and rebuild. Saved scenarios are user data and are never dropped.
NETWORK_TABLES = ("stops", "routes", "connections", "network_source")
