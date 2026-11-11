"""Pydantic response models for the network API."""

from pydantic import BaseModel, ConfigDict


class StopOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    lat: float
    lon: float


class RouteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    color: str


class ConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    route_id: str
    from_stop_id: str
    to_stop_id: str
    travel_time_min: float


class NetworkOut(BaseModel):
    """The whole baseline network in one response (used by the map)."""

    stops: list[StopOut]
    routes: list[RouteOut]
    connections: list[ConnectionOut]
