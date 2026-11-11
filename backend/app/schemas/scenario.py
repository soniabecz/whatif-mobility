"""Scenario: a list of hypothetical changes to the baseline network.

This is the single input format of the simulation. The scenario form (Day 4)
and the AI layer (Day 5) both produce exactly this shape.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

StopId = Annotated[str, Field(min_length=1, max_length=10)]
MAX_CHANGES = 20


class _Change(BaseModel):
    # Reject unknown fields: a typo like "stopid" must fail loudly,
    # not be silently ignored (important when validating AI output).
    model_config = ConfigDict(extra="forbid")


class CloseStop(_Change):
    """Nobody can board, alight or transfer at the stop; buses drive through."""

    type: Literal["close_stop"]
    stop_id: StopId


class RemoveConnection(_Change):
    """The link disappears for every route that uses it."""

    type: Literal["remove_connection"]
    from_stop_id: StopId
    to_stop_id: StopId
    both_directions: bool = True


class ChangeTravelTime(_Change):
    """Set a new travel time (minutes) on the link, for every route using it."""

    type: Literal["change_travel_time"]
    from_stop_id: StopId
    to_stop_id: StopId
    travel_time_min: float = Field(gt=0, le=600, allow_inf_nan=False)
    both_directions: bool = True


ScenarioChange = Annotated[
    CloseStop | RemoveConnection | ChangeTravelTime, Field(discriminator="type")
]


class Scenario(BaseModel):
    """Changes are applied in the given order."""

    model_config = ConfigDict(extra="forbid")

    changes: list[ScenarioChange] = Field(min_length=1, max_length=MAX_CHANGES)
