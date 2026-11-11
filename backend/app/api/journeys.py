"""Journey explorer: one journey before and after a scenario."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.journey import JourneyComparison, JourneyRequest
from app.services import journey_service, network_service
from app.services.simulation_service import ScenarioError

router = APIRouter(prefix="/api", tags=["journeys"])


@router.post("/journeys", response_model=JourneyComparison)
def explain_journey(
    request: JourneyRequest, db: Annotated[Session, Depends(get_db)]
) -> JourneyComparison:
    """Fastest journey before and after the changes. Nothing is stored."""
    baseline = network_service.build_graph_from_db(db)
    try:
        return journey_service.compare_journey(baseline, request)
    except (journey_service.JourneyError, ScenarioError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
