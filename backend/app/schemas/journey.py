"""Journey explorer: one origin -> destination journey before and after a scenario."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.scenario import MAX_CHANGES, ScenarioChange, StopId


class JourneyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin_id: StopId
    destination_id: StopId
    # The scenario travels with the request (stateless, like /api/simulations).
    # An empty list compares the baseline with itself.
    changes: list[ScenarioChange] = Field(default_factory=list, max_length=MAX_CHANGES)

    @model_validator(mode="after")
    def _different_stops(self) -> "JourneyRequest":
        if self.origin_id == self.destination_id:
            raise ValueError("origin and destination must be different stops")
        return self


class JourneyLeg(BaseModel):
    """A stretch travelled on one route without changing bus."""

    route_id: str
    # Every stop the bus passes, in order, including closed stops it drives through.
    stop_ids: list[str]
    travel_time_min: float
    passes_closed_stop_ids: list[str]


class JourneyPlan(BaseModel):
    travel_time_min: float  # = in_vehicle_min + transfers * transfer_penalty_min
    in_vehicle_min: float
    transfers: int  # changes of bus (legs - 1)
    transfer_penalty_min: float
    legs: list[JourneyLeg]


JourneyComparisonStatus = Literal["unchanged", "slower", "faster", "impossible", "unreachable"]


class JourneyComparison(BaseModel):
    origin_id: str
    destination_id: str
    before: JourneyPlan | None  # None only if the stops were never connected
    after: JourneyPlan | None  # None when the journey is no longer possible
    status: JourneyComparisonStatus
    change_min: float | None  # after - before; None unless both exist
    reason: str | None  # why the journey is impossible / unreachable
