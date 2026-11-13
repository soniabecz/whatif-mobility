"""Pydantic response models for the network API."""

from pydantic import BaseModel, ConfigDict


class StopOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    lat: float
    lon: float
    activity: int  # invented demand level: 1 quiet, 2 medium, 3 major


class RouteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    color: str
    headway_min: float  # a bus every N minutes (invented for the sample network)


class ConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    route_id: str
    from_stop_id: str
    to_stop_id: str
    travel_time_min: float


class NetworkSourceOut(BaseModel):
    """Where a real network's data comes from (attribution and dates)."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    publisher: str
    attribution_url: str
    licence: str
    feed_url: str
    feed_created: str
    downloaded: str
    reference_date: str
    method: str


class NetworkOut(BaseModel):
    """The whole baseline network in one response (used by the map).

    ``source`` is None for the invented sample city."""

    stops: list[StopOut]
    routes: list[RouteOut]
    connections: list[ConnectionOut]
    source: NetworkSourceOut | None = None
