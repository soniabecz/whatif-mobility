"""AI service. No real AI calls: a fake model returns canned JSON answers."""

import copy
import json
from types import SimpleNamespace
from typing import Any

import httpx
import groq
import networkx as nx
import pytest
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.schemas.ai import AIInterpretation, strict_json_schema
from app.schemas.scenario import ChangeTravelTime, CloseStop
from app.services.ai_service import (
    AIOutputError,
    AIUnavailableError,
    GroqChatModel,
    build_system_prompt,
    describe_network,
    interpret,
)
from app.services.network_service import build_graph_from_db


class FakeChatModel:
    """Returns a fixed answer and records what it was asked."""

    def __init__(self, answer: dict[str, Any] | str) -> None:
        self.answer = answer if isinstance(answer, str) else json.dumps(answer)
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, system_prompt: str, user_text: str, schema: dict) -> str:
        self.calls.append({"system": system_prompt, "user": user_text, "schema": schema})
        return self.answer


def _ok(*changes: dict[str, Any], message: str = "Understood.") -> dict[str, Any]:
    return {"status": "ok", "changes": list(changes), "message": message}


@pytest.fixture
def sample(db: Session) -> nx.DiGraph:
    return build_graph_from_db(db)


# --- Valid answers ---------------------------------------------------------------

def test_valid_answer_becomes_scenario_changes(sample: nx.DiGraph) -> None:
    model = FakeChatModel(_ok(
        {"type": "close_stop", "stop_id": "CEN"},
        {"type": "change_travel_time", "from_stop_id": "RIV", "to_stop_id": "EST",
         "travel_time_min": 10, "both_directions": True},
        message="Close Central Station and set Riverside–East Gate to 10 min.",
    ))

    result = interpret("close central, riverside to east gate twice as slow", sample, model)

    assert result.status == "ok"
    assert result.message == "Close Central Station and set Riverside–East Gate to 10 min."
    close, retime = result.changes
    assert close == CloseStop(type="close_stop", stop_id="CEN")
    assert isinstance(retime, ChangeTravelTime) and retime.travel_time_min == 10


def test_prompt_contains_network_and_user_text_stays_separate(sample: nx.DiGraph) -> None:
    model = FakeChatModel(_ok({"type": "close_stop", "stop_id": "AIR"}))

    interpret("close the airport", sample, model)

    call = model.calls[0]
    assert call["user"] == "close the airport"  # not mixed into the system prompt
    assert "- AIR: Airport" in call["system"]
    assert "- CEN <-> MKT: 2 min (routes R1, R4)" in call["system"]
    assert call["schema"] == strict_json_schema(AIInterpretation)


def test_interpretation_never_modifies_baseline(sample: nx.DiGraph) -> None:
    snapshot = copy.deepcopy(sample)

    interpret("x", sample, FakeChatModel(_ok({"type": "close_stop", "stop_id": "CEN"})))

    assert list(sample.edges(data=True)) == list(snapshot.edges(data=True))


# --- Content problems become "unclear" -----------------------------------------------

def test_unclear_answer_is_passed_on_without_changes(sample: nx.DiGraph) -> None:
    model = FakeChatModel({
        "status": "unclear",
        "changes": [{"type": "close_stop", "stop_id": "CEN"}],  # ignored
        "message": "Which park do you mean?",
    })

    result = interpret("close the park stop", sample, model)

    assert (result.status, result.changes, result.message) == (
        "unclear", [], "Which park do you mean?")


def test_ok_without_changes_is_unclear(sample: nx.DiGraph) -> None:
    result = interpret("hello", sample, FakeChatModel(_ok(message="")))

    assert result.status == "unclear"
    assert result.message  # a fallback message is provided


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"type": "close_stop", "stop_id": "XXX"}, "unknown stop 'XXX'"),
        ({"type": "remove_connection", "from_stop_id": "NTH", "to_stop_id": "AIR",
          "both_directions": True}, "no connection from 'NTH' to 'AIR'"),
        ({"type": "change_travel_time", "from_stop_id": "RIV", "to_stop_id": "EST",
          "travel_time_min": 0, "both_directions": True}, "not valid"),
        ({"type": "change_travel_time", "from_stop_id": "RIV", "to_stop_id": "EST",
          "travel_time_min": 9999, "both_directions": True}, "not valid"),
    ],
)
def test_invalid_ai_changes_never_reach_the_user(
    sample: nx.DiGraph, change: dict[str, Any], expected: str
) -> None:
    result = interpret("...", sample, FakeChatModel(_ok(change)))

    assert result.status == "unclear"
    assert result.changes == []
    assert expected in result.message


def test_too_many_changes_is_unclear(sample: nx.DiGraph) -> None:
    changes = [{"type": "close_stop", "stop_id": "CEN"}] * 21

    result = interpret("...", sample, FakeChatModel(_ok(*changes)))

    assert result.status == "unclear"


# --- Malformed answers are errors ------------------------------------------------------

@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        json.dumps({"status": "ok", "changes": []}),  # missing message
        json.dumps(_ok({"type": "add_route", "stop_id": "CEN"})),  # unknown type
        json.dumps({"status": "maybe", "changes": [], "message": "?"}),
    ],
)
def test_malformed_answer_raises_output_error(sample: nx.DiGraph, raw: str) -> None:
    with pytest.raises(AIOutputError):
        interpret("...", sample, FakeChatModel(raw))


# --- Prompt and schema helpers ------------------------------------------------------------

def test_describe_network_lists_one_way_links_separately() -> None:
    graph = nx.DiGraph()
    graph.add_node("A", name="Alpha")
    graph.add_node("B", name="Beta")
    graph.add_edge("A", "B", weight=3.0, routes=["R1"])

    text = describe_network(graph)

    assert "- A: Alpha" in text
    assert "- A -> B (one way): 3 min (routes R1)" in text


def test_system_prompt_forbids_estimating_results(sample: nx.DiGraph) -> None:
    assert "never estimate" in build_system_prompt(sample)


def test_strict_schema_is_valid_for_groq_strict_mode() -> None:
    schema = strict_json_schema(AIInterpretation)
    text = json.dumps(schema)

    assert '"title"' not in text and '"const"' not in text
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"status", "changes", "message"}


def test_strict_schema_rejects_optional_fields() -> None:
    class WithDefault(BaseModel):
        model_config = ConfigDict(extra="forbid")
        value: int = 1

    with pytest.raises(ValueError, match="require every property"):
        strict_json_schema(WithDefault)


# --- Groq client: error mapping (no network) ------------------------------------------------

_REQUEST = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def _groq_model(create: Any) -> GroqChatModel:
    model = GroqChatModel(api_key="test-key", model="test-model", timeout_seconds=1)
    model._client = SimpleNamespace(  # type: ignore[assignment]
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    return model


def _raise(error: Exception) -> Any:
    def create(**_kwargs: Any) -> Any:
        raise error
    return create


def _status_error(cls: type[groq.APIStatusError], code: int) -> groq.APIStatusError:
    return cls("error", response=httpx.Response(code, request=_REQUEST), body=None)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (_status_error(groq.AuthenticationError, 401), "rejected the API key"),
        (_status_error(groq.RateLimitError, 429), "rate limit"),
        (groq.APITimeoutError(request=_REQUEST), "too long"),
        (groq.APIConnectionError(request=_REQUEST), "Could not reach"),
        (_status_error(groq.InternalServerError, 500), "HTTP 500"),
    ],
)
def test_provider_errors_become_unavailable(error: Exception, message: str) -> None:
    with pytest.raises(AIUnavailableError, match=message):
        _groq_model(_raise(error)).complete_json("system", "text", {})


def _completion(content: str | None, finish_reason: str = "stop") -> Any:
    message = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


def test_truncated_answer_is_an_output_error() -> None:
    model = _groq_model(lambda **_: _completion('{"status": "o', finish_reason="length"))

    with pytest.raises(AIOutputError, match="cut off"):
        model.complete_json("system", "text", {})


def test_empty_answer_is_an_output_error() -> None:
    with pytest.raises(AIOutputError, match="empty"):
        _groq_model(lambda **_: _completion(None)).complete_json("system", "text", {})


def test_request_uses_strict_json_schema_and_returns_content() -> None:
    sent: dict[str, Any] = {}

    def create(**kwargs: Any) -> Any:
        sent.update(kwargs)
        return _completion('{"ok": true}')

    result = _groq_model(create).complete_json("system", "text", {"type": "object"})

    assert result == '{"ok": true}'
    assert sent["model"] == "test-model"
    assert sent["response_format"]["type"] == "json_schema"
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert sent["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "text"},
    ]
