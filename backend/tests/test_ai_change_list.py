"""The AI knows the current change list (Day 12, part 1).

It answers with operations (remove / replace by number, add at the end); the
backend applies them, checks the numbers and dry-runs the complete new list.
No real AI calls: a fake model returns canned answers.
"""

import json
from typing import Any

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.ai import get_chat_model
from app.main import app
from app.schemas.scenario import Scenario, ScenarioChange
from app.services.ai_service import InvalidChangeListError, build_system_prompt, interpret
from app.services.network_service import build_graph_from_db


class FakeModel:
    def __init__(self, **answer: Any) -> None:
        self.answer = json.dumps({"status": "ok", "remove_numbers": [], "replace": [], "changes": [],
                                  "message": "Done.", **answer})
        self.prompts: list[str] = []

    def complete_json(self, system_prompt: str, user_text: str, schema: dict) -> str:
        self.prompts.append(system_prompt)
        return self.answer


@pytest.fixture
def sample(db: Session) -> nx.DiGraph:
    return build_graph_from_db(db)


def _changes(*changes: dict[str, Any]) -> list[ScenarioChange]:
    return Scenario.model_validate({"changes": list(changes)}).changes


CLOSE_CEN = {"type": "close_stop", "stop_id": "CEN"}
CLOSE_AIR = {"type": "close_stop", "stop_id": "AIR"}
SLOW = {"type": "change_travel_time", "from_stop_id": "RIV", "to_stop_id": "EST", "travel_time_min": 9,
        "both_directions": True}
ROUTE = {"type": "add_route", "route_id": "R5", "name": "Cross Town", "color": "#7c3aed", "headway_min": 12,
         "stop_ids": ["OLD", "MKT", "RIV"], "travel_times_min": [3, 4], "is_loop": False, "both_directions": True}
FREQ_R5 = {"type": "change_frequency", "route_id": "R5", "headway_min": 6}
NEW_STOP = {"type": "add_stop", "stop_id": "N1", "name": "Old Market", "lat": 50.0644, "lon": 19.9366,
            "route_id": "R1", "from_stop_id": "MKT", "to_stop_id": "UNI", "time_from_min": 1.5, "time_to_min": 2}


def _dump(changes: list[ScenarioChange]) -> list[dict[str, Any]]:
    return [change.model_dump() for change in changes]


# --- Operations -----------------------------------------------------------------------

def test_undo_the_last_change(sample: nx.DiGraph) -> None:
    result = interpret("undo the last one", sample, FakeModel(remove_numbers=[2]), _changes(CLOSE_CEN, SLOW))
    assert result.status == "ok"
    assert _dump(result.changes) == _dump(_changes(CLOSE_CEN))
    assert (result.removed, result.replaced, result.added) == ([2], [], 0)


def test_undo_the_only_change_gives_an_empty_list(sample: nx.DiGraph) -> None:
    result = interpret("undo", sample, FakeModel(remove_numbers=[1]), _changes(CLOSE_CEN))
    assert (result.status, result.changes, result.removed) == ("ok", [], [1])


def test_and_also_appends(sample: nx.DiGraph) -> None:
    result = interpret("and also the airport", sample, FakeModel(changes=[CLOSE_AIR]), _changes(CLOSE_CEN))
    assert _dump(result.changes) == _dump(_changes(CLOSE_CEN, CLOSE_AIR))
    assert result.added == 1


def test_replace_keeps_the_position(sample: nx.DiGraph) -> None:
    faster = {**SLOW, "travel_time_min": 7}
    result = interpret("make that 7 instead", sample, FakeModel(replace=[{"number": 1, "change": faster}]),
                       _changes(SLOW, CLOSE_CEN))
    assert _dump(result.changes) == _dump(_changes(faster, CLOSE_CEN))
    assert (result.removed, result.replaced, result.added) == ([], [1], 0)


def test_operations_combine(sample: nx.DiGraph) -> None:
    model = FakeModel(remove_numbers=[1], replace=[{"number": 2, "change": {**SLOW, "travel_time_min": 8}}],
                      changes=[CLOSE_AIR])
    result = interpret("...", sample, model, _changes(CLOSE_CEN, SLOW))
    assert _dump(result.changes) == _dump(_changes({**SLOW, "travel_time_min": 8}, CLOSE_AIR))


def test_later_changes_may_use_a_route_from_the_list(sample: nx.DiGraph) -> None:
    result = interpret("R5 every 6 min", sample, FakeModel(changes=[FREQ_R5]), _changes(ROUTE))
    assert result.status == "ok" and len(result.changes) == 2


# --- Checks ------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("answer", "message"),
    [
        ({"remove_numbers": [3]}, "refers to change 3, but the list has only 2 changes"),
        ({"remove_numbers": [0]}, "refers to change 0"),
        ({"remove_numbers": [1, 1]}, "uses the same change twice"),
        ({"remove_numbers": [1], "replace": [{"number": 1, "change": CLOSE_AIR}]}, "uses the same change twice"),
        ({"replace": [{"number": 2, "change": {**SLOW, "travel_time_min": 0}}]}, "is not valid"),
    ],
)
def test_bad_operations_become_unclear(sample: nx.DiGraph, answer: dict[str, Any], message: str) -> None:
    result = interpret("...", sample, FakeModel(**answer), _changes(CLOSE_CEN, SLOW))
    assert result.status == "unclear" and message in result.message
    assert result.changes == []


def test_numbers_without_a_list(sample: nx.DiGraph) -> None:
    result = interpret("undo", sample, FakeModel(remove_numbers=[1]))
    assert result.status == "unclear" and "the list has no changes" in result.message


def test_removing_what_a_later_change_needs_is_refused(sample: nx.DiGraph) -> None:
    result = interpret("forget the new route", sample, FakeModel(remove_numbers=[1]), _changes(ROUTE, FREQ_R5))
    assert result.status == "unclear"
    assert "resulting list does not fit" in result.message and "unknown route 'R5'" in result.message


def test_at_most_20_changes_after_the_operations(sample: nx.DiGraph) -> None:
    stops = sorted(sample.nodes)
    current = _changes(*({"type": "close_stop", "stop_id": s} for s in stops[:15]))
    more = [{"type": "close_stop", "stop_id": s} for s in stops[15:]]
    fine = interpret("...", sample, FakeModel(changes=more), current)
    assert fine.status == "ok" and len(fine.changes) == 16
    too_many = [SLOW] * 6
    result = interpret("...", sample, FakeModel(changes=too_many), current)
    assert result.status == "unclear" and "21 changes; a scenario can have at most 20" in result.message


def test_an_answer_without_operations_is_unclear(sample: nx.DiGraph) -> None:
    result = interpret("hello", sample, FakeModel(message="Nothing to do."), _changes(CLOSE_CEN))
    assert (result.status, result.message) == ("unclear", "Nothing to do.")


def test_an_invalid_current_list_is_rejected_before_asking_the_ai(sample: nx.DiGraph) -> None:
    model = FakeModel(changes=[CLOSE_AIR])
    with pytest.raises(InvalidChangeListError, match="Change 2 \\(close_stop\\): stop 'CEN' is already closed"):
        interpret("...", sample, model, _changes(CLOSE_CEN, CLOSE_CEN))
    assert model.prompts == []


# --- Prompt ------------------------------------------------------------------------------

def test_prompt_lists_the_current_changes_by_number(sample: nx.DiGraph) -> None:
    prompt = build_system_prompt(sample, _changes(CLOSE_CEN, NEW_STOP, ROUTE, {**FREQ_R5, "route_id": "R1"}))
    assert "1. close_stop: Central Station (CEN)" in prompt
    assert ('2. add_stop: NEW stop N1 "Old Market" on route R1, Market Square (MKT) 1.5 min -> N1 2 min'
            ' -> University (UNI)') in prompt
    assert ('3. add_route: NEW route R5 "Cross Town" (#7c3aed), a bus every 12 min, both directions: '
            'Old Town (OLD) -> Market Square (MKT) -> Riverside (RIV) (3 + 4 min)') in prompt
    assert "4. change_frequency: route R1 a bus every 6 min" in prompt
    # The new route's id and colour are taken: the next ones are offered.
    assert "use route_id R6 " in prompt and "#7c3aed" not in prompt.split("NEW ROUTES:")[1].split("\n")[0]
    assert "remove_numbers" in prompt and "replace" in prompt


def test_prompt_without_changes(sample: nx.DiGraph) -> None:
    assert "CURRENT CHANGES: none yet." in build_system_prompt(sample)


# --- API -----------------------------------------------------------------------------------

def test_api_sends_the_list_and_returns_the_new_one(client: TestClient) -> None:
    model = FakeModel(remove_numbers=[1], changes=[CLOSE_AIR])
    app.dependency_overrides[get_chat_model] = lambda: model
    response = client.post("/api/ai/interpret", json={"text": "airport instead", "current_changes": [CLOSE_CEN]})
    assert response.status_code == 200
    body = response.json()
    assert (body["changes"], body["removed"], body["replaced"], body["added"]) == ([CLOSE_AIR], [1], [], 1)
    assert "1. close_stop: Central Station (CEN)" in model.prompts[0]


def test_api_rejects_an_invalid_list(client: TestClient) -> None:
    app.dependency_overrides[get_chat_model] = lambda: FakeModel()
    response = client.post("/api/ai/interpret", json={"text": "x", "current_changes": [CLOSE_CEN, CLOSE_CEN]})
    assert response.status_code == 422 and "already closed" in response.json()["detail"]
    too_long = client.post("/api/ai/interpret", json={"text": "x", "current_changes": [CLOSE_CEN] * 21})
    assert too_long.status_code == 422
