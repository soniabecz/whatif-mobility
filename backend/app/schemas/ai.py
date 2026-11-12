"""Schemas for the AI layer.

Two separate shapes on purpose:
- ``AIInterpretation``: what the language model must return. Built for Groq's
  strict structured outputs (every field required, no defaults, no numeric
  limits), so it is NOT the Scenario schema itself.
- ``InterpretResponse``: what the API returns. Its changes are real, fully
  validated ``ScenarioChange`` objects (the Day 3 scenario format).
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.scenario import ScenarioChange

MAX_REQUEST_CHARS = 500


class InterpretRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=MAX_REQUEST_CHARS)


class InterpretResponse(BaseModel):
    """``ok``: changes are valid for the network. ``unclear``: no changes;
    ``message`` explains why or asks for clarification."""

    status: Literal["ok", "unclear"]
    changes: list[ScenarioChange]
    message: str


# --- What the language model returns ----------------------------------------

class _AIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")  # -> additionalProperties: false


class AICloseStop(_AIModel):
    type: Literal["close_stop"]
    stop_id: str


class AIRemoveConnection(_AIModel):
    type: Literal["remove_connection"]
    from_stop_id: str
    to_stop_id: str
    both_directions: bool


class AIChangeTravelTime(_AIModel):
    type: Literal["change_travel_time"]
    from_stop_id: str
    to_stop_id: str
    travel_time_min: float
    both_directions: bool


class AIChangeFrequency(_AIModel):
    type: Literal["change_frequency"]
    route_id: str
    headway_min: float


class AIInterpretation(_AIModel):
    status: Literal["ok", "unclear"]
    changes: list[AICloseStop | AIRemoveConnection | AIChangeTravelTime | AIChangeFrequency]
    message: str


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema of ``model`` in the form Groq's strict mode accepts.

    Pydantic output is adjusted: ``title`` keys are dropped and single-value
    ``const`` becomes ``enum`` (the documented keyword). Every object must
    list all its properties as required and forbid extra properties.
    """

    def clean(node: Any) -> Any:
        if isinstance(node, dict):
            result = {k: clean(v) for k, v in node.items() if k != "title"}
            if "const" in result:
                result["enum"] = [result.pop("const")]
            if result.get("type") == "object" and "properties" in result:
                if result.get("additionalProperties") is not False:
                    raise ValueError("strict schema objects must forbid extra properties")
                if set(result.get("required", [])) != set(result["properties"]):
                    raise ValueError("strict schema objects must require every property")
            return result
        if isinstance(node, list):
            return [clean(item) for item in node]
        return node

    return clean(model.model_json_schema())
