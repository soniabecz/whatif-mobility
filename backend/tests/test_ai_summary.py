"""AI summary of results (Day 12, part 2). No real AI: a fake model answers.

The model writes {placeholders}; the backend checks the text (no digits, no
number or ratio words, only known placeholders), retries once, and inserts the
computed values itself.
"""

import json
from typing import Any

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.ai import get_chat_model
from app.main import app
from app.schemas.scenario import Scenario
from app.services.network_service import build_graph_from_db
from app.services.simulation_service import simulate
from app.services.summary_service import Fact, build_facts, check_summary, fill_summary, summarise
from app.services.walking import WalkingModel


class FakeModel:
    """Answers with the given summaries in turn and records the requests."""

    def __init__(self, *summaries: str) -> None:
        self.summaries = list(summaries)
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, system_prompt: str, user_text: str, schema: dict) -> str:
        self.calls.append({"system": system_prompt, "user": user_text, "schema": schema})
        return json.dumps({"summary": self.summaries[len(self.calls) - 1]})


@pytest.fixture
def sample(db: Session) -> nx.DiGraph:
    return build_graph_from_db(db)


CLOSE_CEN = {"type": "close_stop", "stop_id": "CEN"}
SLOW = {"type": "change_travel_time", "from_stop_id": "RIV", "to_stop_id": "EST", "travel_time_min": 9,
        "both_directions": True}


def _result(sample: nx.DiGraph, *changes: dict[str, Any]) -> Any:
    return simulate(sample, Scenario.model_validate({"changes": list(changes)}), 2.0, True, WalkingModel(5, 1000))


def _facts(sample: nx.DiGraph, *changes: dict[str, Any]) -> dict[str, Fact]:
    names = {s: sample.nodes[s]["name"] for s in sample.nodes}
    return {fact.key: fact for fact in build_facts(_result(sample, *changes), names)}


# --- Fact sheet ---------------------------------------------------------------------------

def test_facts_come_from_the_result(sample: nx.DiGraph) -> None:
    result = _result(sample, CLOSE_CEN, SLOW)
    facts = _facts(sample, CLOSE_CEN, SLOW)
    s = result.summary
    assert facts["slower"].value == str(s.slower)
    assert facts["total_journeys"].value == "240"
    assert facts["avg_before"].value == f"{s.average_time_before_min:.1f}"
    change = s.average_time_after_min - s.average_time_before_min
    assert facts["avg_change"].value == f"{abs(change):.1f}" and "longer" in facts["avg_change"].description
    top = result.most_affected_stop_ids[0]
    assert facts["stop1_affected"].description.startswith(f"most affected stop no. 1: {sample.nodes[top]['name']}")
    assert facts["walked"].value == str(s.walked_to_or_from_closed_stop)
    assert facts["change2_minutes"].value == "9"  # the user's own input
    assert "INVENTED demand" in facts["demand_slower_pct"].description
    assert "newly_possible" not in facts and "new_stop_journeys" not in facts  # only facts that exist


def test_largest_increase_names_the_journey(sample: nx.DiGraph) -> None:
    result = _result(sample, SLOW)
    j = result.summary.largest_increase
    assert j is not None
    fact = _facts(sample, SLOW)["largest_increase"]
    assert fact.value == f"{j.change_min:.1f}"
    assert sample.nodes[j.origin_id]["name"] in fact.description


# --- Check ----------------------------------------------------------------------------------

FACTS = [Fact("slower", "34", ""), Fact("avg_before", "12.3", ""), Fact("stop1_affected", "20", "")]


@pytest.mark.parametrize(
    "text",
    [
        "{slower} journeys get slower; the average was {avg_before} min.",
        "Route R5 and the new stop N1 help; {stop1_affected} journeys at Central Station change.",
        "Some journeys get much longer, one of them a lot.",  # "one" is allowed (no count)
    ],
)
def test_acceptable_texts(text: str) -> None:
    assert check_summary(text, FACTS) == []


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("34 journeys get slower.", "numbers written directly: 34"),
        ("{slower} journeys, about 12.5 min each.", "numbers written directly: 12.5"),
        ("{slower} journeys get slower, {faster} faster.", "unknown placeholders: {faster}"),
        ("Twice as many journeys get slower.", "number or ratio words: twice"),
        ("Two stops are hit hardest; journeys take half as long.", "number or ratio words: two, half"),
        ("{slower} journeys {get slower.", "braces outside a placeholder"),
        ("   ", "the summary is empty"),
        ("{slower} " + "x" * 1300, "longer than 1200 characters"),
    ],
)
def test_rejected_texts(text: str, problem: str) -> None:
    assert any(problem in found for found in check_summary(text, FACTS))


def test_fill_inserts_the_computed_values() -> None:
    assert fill_summary("{slower} slower; before {avg_before} min. ", FACTS) == "34 slower; before 12.3 min."


# --- The call, with retry -------------------------------------------------------------------

def test_an_honest_summary_is_filled_in(sample: nx.DiGraph) -> None:
    result = _result(sample, CLOSE_CEN)
    model = FakeModel("{slower} journeys get slower and {impossible} become impossible.")
    response = summarise(sample, result, model)
    assert response.status == "ok"
    assert response.summary == (
        f"{result.summary.slower} journeys get slower and {result.summary.impossible} become impossible."
    )
    assert len(model.calls) == 1
    prompt = model.calls[0]["system"]
    assert f"- {{slower}} = {result.summary.slower}: journeys that get slower" in prompt
    assert "1. close_stop: Central Station (CEN)" in prompt
    assert "changed_journeys" not in prompt and "origin_id" not in prompt  # no raw journey list


def test_one_retry_names_the_problems(sample: nx.DiGraph) -> None:
    model = FakeModel("About 40 journeys get slower.", "{slower} journeys get slower.")
    response = summarise(sample, _result(sample, CLOSE_CEN), model)
    assert response.status == "ok" and len(model.calls) == 2
    assert "numbers written directly: 40" in model.calls[1]["user"]


def test_withheld_after_two_bad_answers(sample: nx.DiGraph) -> None:
    model = FakeModel("About 40 journeys get slower.", "Twice as many journeys get slower.")
    response = summarise(sample, _result(sample, CLOSE_CEN), model)
    assert (response.status, response.summary) == ("withheld", None)
    assert "number or ratio words: twice" in response.message
    assert "The results above are complete without it." in response.message


# --- API ---------------------------------------------------------------------------------------

def test_api_simulates_itself_and_returns_the_summary(client: TestClient) -> None:
    app.dependency_overrides[get_chat_model] = lambda: FakeModel("{total_journeys} journeys; {slower} slower.")
    response = client.post("/api/ai/summary", json={"changes": [CLOSE_CEN]})
    assert response.status_code == 200
    simulation = client.post("/api/simulations", json={"changes": [CLOSE_CEN]}).json()
    assert response.json() == {
        "status": "ok",
        "summary": f"240 journeys; {simulation['summary']['slower']} slower.",
        "message": "",
    }


def test_api_errors(client: TestClient) -> None:
    app.dependency_overrides[get_chat_model] = lambda: FakeModel("x")
    bad = client.post("/api/ai/summary", json={"changes": [{"type": "close_stop", "stop_id": "XYZ"}]})
    assert bad.status_code == 422 and "unknown stop 'XYZ'" in bad.json()["detail"]
    app.dependency_overrides.pop(get_chat_model)
    not_configured = client.post("/api/ai/summary", json={"changes": [CLOSE_CEN]})
    assert not_configured.status_code == 503 and "not configured" in not_configured.json()["detail"]
