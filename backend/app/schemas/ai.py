"""Schemas for the AI layer.

Two separate shapes on purpose:
- ``AIInterpretation``: what the language model must return. Built for Groq's
  strict structured outputs (every field required, no defaults, no numeric
  limits), so it is NOT the Scenario schema itself.
- ``InterpretResponse``: what the API returns. Its changes are real, fully
  validated ``ScenarioChange`` objects (the Day 3 scenario format).

The AI knows the user's current change list (Day 12). It never rewrites that
list: it answers with operations (remove / replace by number, add at the end),
which the backend applies and validates, so every effect is explicit.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.scenario import MAX_CHANGES, ScenarioChange

MAX_REQUEST_CHARS = 500


class InterpretRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=MAX_REQUEST_CHARS)
    # The scenario being built, in order; the AI may remove, replace or add to it.
    current_changes: list[ScenarioChange] = Field(default_factory=list, max_length=MAX_CHANGES)


class InterpretResponse(BaseModel):
    """``ok``: ``changes`` is the complete NEW change list (it may be empty, e.g.
    after "undo the only change"), valid for the network; ``removed`` and
    ``replaced`` are numbers (1-based) in the current list, ``added`` how many
    changes were appended. ``unclear``: nothing changes (``changes`` is empty);
    ``message`` explains why or asks for clarification."""

    status: Literal["ok", "unclear"]
    changes: list[ScenarioChange]
    removed: list[int] = Field(default_factory=list)
    replaced: list[int] = Field(default_factory=list)
    added: int = 0
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


class AIAddConnection(_AIModel):
    type: Literal["add_connection"]
    route_id: str
    from_stop_id: str
    to_stop_id: str
    travel_time_min: float
    both_directions: bool


class AIAddRoute(_AIModel):
    type: Literal["add_route"]
    route_id: str
    name: str
    color: str
    headway_min: float
    stop_ids: list[str]
    travel_times_min: list[float]
    is_loop: bool
    both_directions: bool


AIChange = (
    AICloseStop
    | AIRemoveConnection
    | AIChangeTravelTime
    | AIChangeFrequency
    | AIAddConnection
    | AIAddRoute
)


class AIReplacement(_AIModel):
    number: int  # of the change in the current list
    change: AIChange


class AIInterpretation(_AIModel):
    status: Literal["ok", "unclear"]
    remove_numbers: list[int]  # current changes to remove
    replace: list[AIReplacement]  # current changes to replace, in place
    changes: list[AIChange]  # new changes, appended at the end
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


# --- AI summary of results (Day 12, part 2) ----------------------------------

class SummaryResponse(BaseModel):
    """``ok``: ``summary`` is the AI's text with every number inserted by the
    backend from the computed results. ``withheld``: the AI did not keep to the
    rules (twice); ``summary`` is None and ``message`` says why."""

    status: Literal["ok", "withheld"]
    summary: str | None
    message: str


class AISummary(_AIModel):
    """What the language model returns: text with {placeholders}, no digits."""

    summary: str
