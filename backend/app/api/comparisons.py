"""Compare two scenarios (Day 13). Both are simulated here; nothing is stored."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.schemas.saved_scenario import ComparisonRequest, ComparisonResult
from app.schemas.scenario import Scenario
from app.services import comparison_service, network_service
from app.services.simulation_service import ScenarioError

router = APIRouter(prefix="/api", tags=["comparisons"])


@router.post("/comparisons", response_model=ComparisonResult)
def compare_scenarios(
    request: ComparisonRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ComparisonResult:
    baseline = network_service.build_graph_from_db(db)
    try:
        return comparison_service.compare(
            baseline,
            Scenario(changes=request.a),
            Scenario(changes=request.b),
            settings.transfer_penalty_min,
            settings.include_waiting,
            settings.walking,
        )
    except ScenarioError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
