"""Read-only endpoints for the baseline network."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.network import ConnectionOut, NetworkOut, NetworkSourceOut, RouteOut, StopOut
from app.services import network_service

router = APIRouter(prefix="/api", tags=["network"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/stops", response_model=list[StopOut])
def get_stops(db: DbSession) -> list[StopOut]:
    return [StopOut.model_validate(s) for s in network_service.list_stops(db)]


@router.get("/routes", response_model=list[RouteOut])
def get_routes(db: DbSession) -> list[RouteOut]:
    return [RouteOut.model_validate(r) for r in network_service.list_routes(db)]


@router.get("/network", response_model=NetworkOut)
def get_network(db: DbSession) -> NetworkOut:
    source = network_service.get_source(db)
    return NetworkOut(
        source=NetworkSourceOut.model_validate(source) if source else None,
        stops=[StopOut.model_validate(s) for s in network_service.list_stops(db)],
        routes=[RouteOut.model_validate(r) for r in network_service.list_routes(db)],
        connections=[
            ConnectionOut.model_validate(c)
            for c in network_service.list_connections(db)
        ],
    )
