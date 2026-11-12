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


class NewStops(BaseModel):
    """Journeys to or from stops ADDED by the scenario. They have no "before",
    so they are reported here and kept out of every other figure."""

    stop_ids: list[str]
    journeys: int  # ordered pairs between open stops that involve a new stop
    possible: int
    average_time_min: float | None  # over the possible ones


class DemandWeighted(BaseModel):
    """The same figures weighted by INVENTED demand: a journey weighs
    origin activity x destination activity (stop levels 1-3). Only shares
    and averages: absolute passenger numbers would be fake data."""

    unchanged_pct: float  # share of all trips, 0-100
    slower_pct: float
    faster_pct: float
    impossible_pct: float
    newly_possible_pct: float
    to_or_from_closed_stop_pct: float
    average_time_before_min: float | None  # over journeys possible before and after
    average_time_after_min: float | None


class SimulationSummary(BaseModel):
    total_journeys: int  # every ordered pair of distinct stops
    unchanged: int
    slower: int
    faster: int
    impossible: int
    # Impossible in the baseline, possible after (only an added connection can
    # do this); no "before" time, so not in changed_journeys or the averages.
    newly_possible: int
    to_or_from_closed_stop: int  # excluded from all other figures
    # Journeys to/from a closed stop compared WITH walking (included in the
    # figures above); 0 when walking is off.
    walked_to_or_from_closed_stop: int
    # Averages and total over journeys possible both before and after.
    average_time_before_min: float | None
    average_time_after_min: float | None
    total_time_change_min: float
    largest_increase: JourneyChange | None
    transfer_penalty_min: float  # minutes counted per change of bus
    include_waiting: bool  # True: half the headway is waited at every boarding
    demand_weighted: DemandWeighted
    new_stops: NewStops | None  # None when the scenario adds no stop


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
