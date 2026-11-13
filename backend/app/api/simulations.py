"""Run a scenario against the baseline network."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.schemas.scenario import Scenario
from app.schemas.simulation import SimulationResult
from app.schemas.scenario import AddStop
from app.services import export_service, network_service, simulation_service

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


@router.post(
    "/simulations/csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "Every changed journey"}},
)
def changed_journeys_csv(
    scenario: Scenario,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Every changed journey as CSV (a result lists only the largest changes)."""
    baseline = network_service.build_graph_from_db(db)
    try:
        result = simulation_service.simulate(
            baseline,
            scenario,
            settings.transfer_penalty_min,
            settings.include_waiting,
            settings.walking,
            max_changed=None,
        )
    except simulation_service.ScenarioError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    names = {stop_id: baseline.nodes[stop_id]["name"] for stop_id in baseline.nodes}
    names |= {c.stop_id: c.name for c in scenario.changes if isinstance(c, AddStop)}
    return Response(
        export_service.changed_journeys_csv(result.changed_journeys, names),
        media_type="text/csv; charset=utf-8",
    )
