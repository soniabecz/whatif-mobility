"""Saved scenarios (Day 13): only change lists are stored; results are recomputed."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.saved_scenario import SavedScenarioIn, SavedScenarioInfo, SavedScenarioOut
from app.services import network_service, scenario_store
from app.services.simulation_service import ScenarioError

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])

DB = Annotated[Session, Depends(get_db)]


def _not_found(error: scenario_store.ScenarioNotFoundError) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=str(error))


def _write_error(error: Exception) -> HTTPException:
    if isinstance(error, scenario_store.ScenarioNameTakenError):
        return HTTPException(status.HTTP_409_CONFLICT, detail=str(error))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.get("", response_model=list[SavedScenarioInfo])
def list_saved(db: DB) -> list[SavedScenarioInfo]:
    """Newest first; each checked against the current network (``fits``)."""
    return scenario_store.list_scenarios(db, network_service.build_graph_from_db(db))


@router.post("", response_model=SavedScenarioOut, status_code=status.HTTP_201_CREATED)
def save(data: SavedScenarioIn, db: DB) -> SavedScenarioOut:
    try:
        return scenario_store.create_scenario(db, network_service.build_graph_from_db(db), data)
    except (ScenarioError, scenario_store.ScenarioNameTakenError) as error:
        raise _write_error(error) from error


@router.get("/{scenario_id}", response_model=SavedScenarioOut)
def get_saved(scenario_id: int, db: DB) -> SavedScenarioOut:
    try:
        return scenario_store.get_scenario(db, network_service.build_graph_from_db(db), scenario_id)
    except scenario_store.ScenarioNotFoundError as error:
        raise _not_found(error) from error


@router.put("/{scenario_id}", response_model=SavedScenarioOut)
def overwrite(scenario_id: int, data: SavedScenarioIn, db: DB) -> SavedScenarioOut:
    try:
        return scenario_store.update_scenario(db, network_service.build_graph_from_db(db), scenario_id, data)
    except scenario_store.ScenarioNotFoundError as error:
        raise _not_found(error) from error
    except (ScenarioError, scenario_store.ScenarioNameTakenError) as error:
        raise _write_error(error) from error


@router.delete("/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(scenario_id: int, db: DB) -> Response:
    try:
        scenario_store.delete_scenario(db, scenario_id)
    except scenario_store.ScenarioNotFoundError as error:
        raise _not_found(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
