"""POST /api/ai/interpret with a fake model (never calls the real AI)."""

import json
from typing import Any

from fastapi.testclient import TestClient

from app.api.ai import get_chat_model
from app.config import Settings, get_settings
from app.main import app
from app.services.ai_service import AIOutputError, AIUnavailableError


class FakeChatModel:
    def __init__(self, answer: dict[str, Any] | Exception) -> None:
        self.answer = answer

    def complete_json(self, system_prompt: str, user_text: str, schema: dict) -> str:
        if isinstance(self.answer, Exception):
            raise self.answer
        # Operations on the change list default to none (Day 12).
        return json.dumps({"remove_numbers": [], "replace": [], **self.answer})


def _use_model(answer: dict[str, Any] | Exception) -> None:
    app.dependency_overrides[get_chat_model] = lambda: FakeChatModel(answer)


def test_interpret_returns_validated_changes(client: TestClient) -> None:
    _use_model({
        "status": "ok",
        "changes": [{"type": "remove_connection", "from_stop_id": "TEC",
                     "to_stop_id": "AIR", "both_directions": True}],
        "message": "Remove the link between Tech Park and Airport.",
    })

    response = client.post("/api/ai/interpret", json={"text": "cut off the airport"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "changes": [{"type": "remove_connection", "from_stop_id": "TEC",
                     "to_stop_id": "AIR", "both_directions": True}],
        "removed": [],
        "replaced": [],
        "added": 1,
        "message": "Remove the link between Tech Park and Airport.",
    }


def test_returned_changes_can_be_simulated(client: TestClient) -> None:
    _use_model({"status": "ok", "changes": [{"type": "close_stop", "stop_id": "CEN"}],
                "message": "Close Central Station."})

    changes = client.post("/api/ai/interpret", json={"text": "close central"}).json()["changes"]
    response = client.post("/api/simulations", json={"changes": changes})

    assert response.status_code == 200
    assert response.json()["summary"]["to_or_from_closed_stop"] == 30


def test_missing_api_key_returns_503(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, groq_api_key=None  # type: ignore[call-arg]
    )

    response = client.post("/api/ai/interpret", json={"text": "close central"})

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_provider_unavailable_returns_503(client: TestClient) -> None:
    _use_model(AIUnavailableError("The AI took too long to answer. Please try again."))

    response = client.post("/api/ai/interpret", json={"text": "close central"})

    assert response.status_code == 503
    assert response.json() == {"detail": "The AI took too long to answer. Please try again."}


def test_malformed_ai_output_returns_502(client: TestClient) -> None:
    _use_model(AIOutputError("The AI returned an answer in an unexpected format."))

    response = client.post("/api/ai/interpret", json={"text": "close central"})

    assert response.status_code == 502


def test_request_text_is_validated(client: TestClient) -> None:
    _use_model({"status": "unclear", "changes": [], "message": "?"})

    assert client.post("/api/ai/interpret", json={"text": "   "}).status_code == 422
    assert client.post("/api/ai/interpret", json={"text": "x" * 501}).status_code == 422
    assert client.post("/api/ai/interpret", json={}).status_code == 422
