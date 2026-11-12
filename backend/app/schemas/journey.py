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
    travel_time_min: float  # time on the bus
    wait_min: float  # expected wait before boarding (0 when waiting is not modelled)
    passes_closed_stop_ids: list[str]


class WalkLeg(BaseModel):
    """Walking to or from a closed stop (straight line x detour factor)."""

    from_stop_id: str
    to_stop_id: str
    distance_m: float
    minutes: float


class JourneyPlan(BaseModel):
    # = walk_min + in_vehicle_min + wait_min + transfers * transfer_penalty_min
    travel_time_min: float
    in_vehicle_min: float
    wait_min: float  # waiting at every boarding (0 when waiting is not modelled)
    walk_min: float  # walking to/from a closed stop (0 for ordinary journeys)
    walk_start: WalkLeg | None  # walk from a closed origin (or the whole way)
    walk_end: WalkLeg | None  # walk to a closed destination
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
