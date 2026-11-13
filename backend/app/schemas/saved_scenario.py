"""Saved scenarios and comparisons (Day 13)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.scenario import MAX_CHANGES, ScenarioChange
from app.schemas.simulation import SimulationSummary


class SavedScenarioIn(BaseModel):
    """Create or overwrite: a name and a change list (1-20 changes)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    changes: list[ScenarioChange] = Field(min_length=1, max_length=MAX_CHANGES)

    @field_validator("name")
    @classmethod
    def _strip(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("the scenario needs a name")
        return name


class SavedScenarioInfo(BaseModel):
    """One row of the list. ``fits`` = it applies to the CURRENT network
    (checked on every listing); ``problem`` says why not."""

    id: int
    name: str
    change_count: int
    created_at: datetime
    updated_at: datetime
    fits: bool
    problem: str | None


class SavedScenarioOut(SavedScenarioInfo):
    changes: list[ScenarioChange]  # empty if the stored list can no longer be read


class ComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a: list[ScenarioChange] = Field(min_length=1, max_length=MAX_CHANGES)
    b: list[ScenarioChange] = Field(min_length=1, max_length=MAX_CHANGES)


class JourneyDifference(BaseModel):
    """One journey between baseline stops under both scenarios (None = impossible)."""

    origin_id: str
    destination_id: str
    time_baseline_min: float | None
    time_a_min: float | None
    time_b_min: float | None
    difference_min: float | None  # A - B; None when only one of them is possible


class ComparisonResult(BaseModel):
    """Every number is computed by comparison_service from two fresh simulations.

    Journeys are the baseline's ordered stop pairs; a journey to or from a stop
    that A or B closes (with walking off) is left out of the journey counts."""

    a: SimulationSummary
    b: SimulationSummary
    compared_journeys: int  # included in both
    same: int
    a_faster: int
    b_faster: int
    only_possible_in_a: int
    only_possible_in_b: int
    impossible_in_both: int
    largest_differences: list[JourneyDifference]  # up to 10, largest first
