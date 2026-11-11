"""Simulation result. Every number here is computed by simulation_service."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.scenario import Scenario

JourneyStatus = Literal["slower", "faster", "impossible"]


class JourneyChange(BaseModel):
    """One origin -> destination journey whose fastest travel time changed."""

    origin_id: str
    destination_id: str
    time_before_min: float
    time_after_min: float | None  # None = no longer possible
    change_min: float | None  # after - before; None when impossible
    status: JourneyStatus


class SimulationSummary(BaseModel):
    total_journeys: int  # every ordered pair of distinct stops
    unchanged: int
    slower: int
    faster: int
    impossible: int
    to_or_from_closed_stop: int  # excluded from all other figures
    # Averages and total over journeys possible both before and after.
    average_time_before_min: float | None
    average_time_after_min: float | None
    total_time_change_min: float
    largest_increase: JourneyChange | None
    transfer_penalty_min: float  # minutes counted per change of bus


class StopImpact(BaseModel):
    """Effect on journeys starting or ending at one stop."""

    stop_id: str
    closed: bool
    affected_journeys: int  # slower + faster + impossible
    impossible_journeys: int
    average_change_min: float | None  # over affected journeys still possible


class SimulationResult(BaseModel):
    scenario: Scenario
    summary: SimulationSummary
    changed_journeys: list[JourneyChange]
    stop_impacts: list[StopImpact]  # every stop, sorted by id
    most_affected_stop_ids: list[str]  # up to 5, most affected first
