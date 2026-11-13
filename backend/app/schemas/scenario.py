"""Scenario: a list of hypothetical changes to the baseline network.

This is the single input format of the simulation. The scenario form (Day 4)
and the AI layer (Day 5) both produce exactly this shape.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

StopId = Annotated[str, Field(min_length=1, max_length=10)]
RouteId = Annotated[str, Field(min_length=1, max_length=10)]
MAX_CHANGES = 20
MIN_HEADWAY_MIN = 1
MAX_HEADWAY_MIN = 120
MAX_ROUTE_STOPS = 30
# Colours offered for new routes (the form and the AI pick one not yet used).
# Chosen to stay apart from the sample routes' red, blue, green and orange.
NEW_ROUTE_COLORS = ("#7c3aed", "#db2777", "#0d9488", "#92400e", "#ca8a04", "#475569")


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


class ChangeFrequency(_Change):
    """The route runs every ``headway_min`` minutes (affects waiting time only)."""

    type: Literal["change_frequency"]
    route_id: RouteId
    headway_min: float = Field(ge=MIN_HEADWAY_MIN, le=MAX_HEADWAY_MIN, allow_inf_nan=False)


class AddConnection(_Change):
    """An existing route also runs directly between two stops (an extension or
    a shortcut). At least one of the stops must already be on the route."""

    type: Literal["add_connection"]
    route_id: RouteId
    from_stop_id: StopId
    to_stop_id: StopId
    travel_time_min: float = Field(gt=0, le=600, allow_inf_nan=False)
    both_directions: bool = True

    @model_validator(mode="after")
    def _different_stops(self) -> "AddConnection":
        if self.from_stop_id == self.to_stop_id:
            raise ValueError("a connection needs two different stops")
        return self


class AddStop(_Change):
    """A new stop inserted into a route between two consecutive stops: the
    route's buses now run from -> new stop -> to (and back, if the route runs
    both ways). The user gives both travel times."""

    type: Literal["add_stop"]
    stop_id: StopId
    name: str = Field(min_length=1, max_length=100)
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    route_id: RouteId
    from_stop_id: StopId
    to_stop_id: StopId
    time_from_min: float = Field(gt=0, le=600, allow_inf_nan=False)  # from_stop -> new stop
    time_to_min: float = Field(gt=0, le=600, allow_inf_nan=False)  # new stop -> to_stop

    @model_validator(mode="after")
    def _distinct_stops(self) -> "AddStop":
        if len({self.stop_id, self.from_stop_id, self.to_stop_id}) < 3:
            raise ValueError("the new stop and the two stops it goes between must all differ")
        if not self.name.strip():
            raise ValueError("the new stop needs a name")
        return self


class AddRoute(_Change):
    """A new bus line through stops that exist (or were added by an earlier
    change), in order. ``travel_times_min[i]`` is the time from stop i to
    stop i+1; a loop has one more, from the last stop back to the first.
    The user gives every time and the headway (nothing is guessed)."""

    type: Literal["add_route"]
    route_id: RouteId
    name: str = Field(min_length=1, max_length=100)
    # Display only (the map); not used by the simulation.
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    headway_min: float = Field(ge=MIN_HEADWAY_MIN, le=MAX_HEADWAY_MIN, allow_inf_nan=False)
    stop_ids: list[StopId] = Field(min_length=2, max_length=MAX_ROUTE_STOPS)
    travel_times_min: list[Annotated[float, Field(gt=0, le=600, allow_inf_nan=False)]]
    is_loop: bool = False
    both_directions: bool = True

    @model_validator(mode="after")
    def _consistent(self) -> "AddRoute":
        if not self.name.strip():
            raise ValueError("the new route needs a name")
        if len(set(self.stop_ids)) != len(self.stop_ids):
            raise ValueError("a route cannot stop at the same stop twice")
        if self.is_loop and len(self.stop_ids) < 3:
            raise ValueError("a loop needs at least 3 stops")
        stretches = len(self.stop_ids) - (0 if self.is_loop else 1)
        if len(self.travel_times_min) != stretches:
            raise ValueError(
                f"{len(self.stop_ids)} stops need {stretches} travel times"
                f"{' (a loop includes the way back to the first stop)' if self.is_loop else ''}"
                f", got {len(self.travel_times_min)}"
            )
        return self

    def stretches(self) -> list[tuple[str, str, float]]:
        """(from, to, minutes) in the route's own direction."""
        stops = self.stop_ids
        starts = stops if self.is_loop else stops[:-1]
        ends = stops[1:] + ([stops[0]] if self.is_loop else [])
        return list(zip(starts, ends, self.travel_times_min, strict=True))


ScenarioChange = Annotated[
    CloseStop
    | RemoveConnection
    | ChangeTravelTime
    | ChangeFrequency
    | AddConnection
    | AddStop
    | AddRoute,
    Field(discriminator="type"),
]


class Scenario(BaseModel):
    """Changes are applied in the given order."""

    model_config = ConfigDict(extra="forbid")

    changes: list[ScenarioChange] = Field(min_length=1, max_length=MAX_CHANGES)
