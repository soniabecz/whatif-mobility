"""Validation of the scenario input format."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.scenario import ChangeTravelTime, CloseStop, RemoveConnection, Scenario


def test_parses_all_three_change_types() -> None:
    scenario = Scenario.model_validate(
        {
            "changes": [
                {"type": "close_stop", "stop_id": "CEN"},
                {"type": "remove_connection", "from_stop_id": "MKT", "to_stop_id": "CEN"},
                {
                    "type": "change_travel_time",
                    "from_stop_id": "RIV",
                    "to_stop_id": "EST",
                    "travel_time_min": 9,
                    "both_directions": False,
                },
            ]
        }
    )

    close, remove, retime = scenario.changes
    assert isinstance(close, CloseStop)
    assert isinstance(remove, RemoveConnection) and remove.both_directions is True
    assert isinstance(retime, ChangeTravelTime) and retime.both_directions is False


@pytest.mark.parametrize(
    "change",
    [
        {"type": "add_route", "stop_id": "CEN"},  # unknown type
        {"stop_id": "CEN"},  # missing type
        {"type": "close_stop"},  # missing stop
        {"type": "close_stop", "stop_id": ""},  # empty stop id
        {"type": "close_stop", "stop_id": "CEN", "stopid": "X"},  # unknown field
        {"type": "change_travel_time", "from_stop_id": "A", "to_stop_id": "B",
         "travel_time_min": 0},
        {"type": "change_travel_time", "from_stop_id": "A", "to_stop_id": "B",
         "travel_time_min": -3},
        {"type": "change_travel_time", "from_stop_id": "A", "to_stop_id": "B",
         "travel_time_min": float("inf")},
        {"type": "change_travel_time", "from_stop_id": "A", "to_stop_id": "B"},
    ],
)
def test_invalid_change_is_rejected(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Scenario.model_validate({"changes": [change]})


def test_scenario_needs_at_least_one_change() -> None:
    with pytest.raises(ValidationError):
        Scenario.model_validate({"changes": []})
