"""SQLAlchemy models. Importing this package registers all tables on Base."""

from app.models.network import Connection, NetworkSource, PatternStop, Route, RoutePattern, Stop
from app.models.scenario import SavedScenario

__all__ = ["Connection", "NetworkSource", "PatternStop", "Route", "RoutePattern", "SavedScenario", "Stop"]

# Tables holding only generated network data (sample or imported): safe to
# drop and rebuild. Saved scenarios are user data and are never dropped.
NETWORK_TABLES = ("stops", "routes", "connections", "route_patterns", "pattern_stops", "network_source")
