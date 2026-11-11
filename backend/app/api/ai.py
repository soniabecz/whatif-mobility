"""Natural-language scenario input. Returns changes for review; runs nothing."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.schemas.ai import InterpretRequest, InterpretResponse
from app.services import ai_service, network_service

router = APIRouter(prefix="/api/ai", tags=["ai"])


def get_chat_model(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ai_service.ChatModel:
    """FastAPI dependency (overridden in tests with a fake model)."""
    if not settings.ai_enabled or settings.groq_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI is not configured. Add GROQ_API_KEY to backend/.env "
            "and restart the backend. The scenario form still works.",
        )
    return ai_service.get_groq_model(
        settings.groq_api_key.get_secret_value(),
        settings.ai_model,
        settings.ai_timeout_seconds,
    )


@router.post("/interpret", response_model=InterpretResponse)
def interpret_text(
    request: InterpretRequest,
    db: Annotated[Session, Depends(get_db)],
    model: Annotated[ai_service.ChatModel, Depends(get_chat_model)],
) -> InterpretResponse:
    baseline = network_service.build_graph_from_db(db)
    try:
        return ai_service.interpret(request.text, baseline, model)
    except ai_service.AIUnavailableError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except ai_service.AIOutputError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
