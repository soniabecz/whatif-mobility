"""Run a scenario against the baseline network."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.schemas.scenario import Scenario
from app.schemas.simulation import SimulationResult
from app.services import network_service, simulation_service

router = APIRouter(prefix="/api", tags=["simulations"])


@router.post("/simulations", response_model=SimulationResult)
def run_simulation(
    scenario: Scenario,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SimulationResult:
    """Simulate the scenario. Nothing is stored; the baseline is unchanged."""
    baseline = network_service.build_graph_from_db(db)
    try:
        return simulation_service.simulate(
            baseline,
            scenario,
            settings.transfer_penalty_min,
            settings.include_waiting,
            settings.walking,
        )
    except simulation_service.ScenarioError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
