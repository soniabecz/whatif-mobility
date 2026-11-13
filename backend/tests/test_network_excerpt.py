"""AI prompt excerpts for big networks (Day 14, step B3).

A whole city's description does not fit the AI provider's free tier, so the
prompt lists only the stations and lines the request (or the change list) is
about. Station names match without diacritics and by word stems (Polish cases).
"""

import json
from typing import Any

import networkx as nx
import pytest

from app.models import Connection, Route, Stop
from app.schemas.scenario import Scenario
from app.services import ai_service
from app.services.ai_service import build_system_prompt, describe_network, interpret
from app.services.network_excerpt import (
    describe_excerpt,
    describe_lines,
    matching_routes,
    matching_stations,
    normalise,
)
from app.services.network_service import build_graph

NAMES = {
    "S1": "Brama Wyżynna", "S2": "Bramińskiego", "S3": "Dworzec Główny", "S4": "Przystań",
    "S5": "Stogi", "S6": "Łostowice Świętokrzyska", "S7": "Politechnika SKM", "S8": "Bratki",
}


def _network(extra_stops: int = 0) -> nx.DiGraph:
    """T8: S1-S2-S3-S4 (+ extra stops S100...), B199: S3-S5-S6, T10: S7-S8 one way."""
    names = dict(NAMES) | {f"S{100 + i}": f"Przystanek numer {i}" for i in range(extra_stops)}
    stops = [Stop(id=s, name=n, lat=0.0, lon=0.0, activity=1) for s, n in names.items()]
    t8 = ["S1", "S2", "S3", "S4", *(f"S{100 + i}" for i in range(extra_stops))]
    links = []
    for a, b in zip(t8, t8[1:]):
        links += [Connection(route_id="T8", from_stop_id=a, to_stop_id=b, travel_time_min=2),
                  Connection(route_id="T8", from_stop_id=b, to_stop_id=a, travel_time_min=3)]
    for a, b in (("S3", "S5"), ("S5", "S6")):
        links += [Connection(route_id="B199", from_stop_id=a, to_stop_id=b, travel_time_min=4),
                  Connection(route_id="B199", from_stop_id=b, to_stop_id=a, travel_time_min=4)]
    links.append(Connection(route_id="T10", from_stop_id="S7", to_stop_id="S8", travel_time_min=1))
    routes = [Route(id=r, name=f"Line {r}", color="#000000", headway_min=h)
              for r, h in (("T8", 12), ("B199", 30), ("T10", 10))]
    return build_graph(stops, links, routes)


NET = _network()


def _names(stop_ids: set[str]) -> list[str]:
    return sorted(NAMES[s] for s in stop_ids)


def test_normalise() -> None:
    assert normalise("Łostowice – Świętokrzyska!") == "lostowice swietokrzyska"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("close Brama Wyżynna", ["Brama Wyżynna"]),
        ("Zamknij przystanek przy Bramie Wyżynnej", ["Brama Wyżynna"]),  # case endings; "przystanek" ignored
        ("zamknij przystanek Dworca Głównego", ["Dworzec Główny"]),       # dworzec/dworca
        ("close lostowice swietokrzyska", ["Łostowice Świętokrzyska"]),   # no diacritics typed
        ("zamknij Politechnikę", ["Politechnika SKM"]),                   # short words (SKM) optional
        ("close the stop", []),                                           # nothing specific
        ("make Brama slower", []),                                        # one word of two is not enough
    ],
)
def test_matching_stations(text: str, expected: list[str]) -> None:
    assert _names(matching_stations(NET, text)) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("tramwaj 8 co 5 minut", {"T8"}),   # "5 minut" is a time, not line 5
        ("bus 199 every 10 min", {"B199"}),
        ("T10 twice as often", {"T10"}),
        ("close Brama Wyżynna", set()),
    ],
)
def test_matching_routes(text: str, expected: set[str]) -> None:
    assert matching_routes(NET, text) == expected


def test_excerpt_shows_the_stations_lines_around_them() -> None:
    big = _network(extra_stops=20)
    text = describe_excerpt(big, "close Brama Wyżynna")
    assert "NETWORK EXCERPT: the network has 28 stops and 3 routes" in text
    assert "- S1: Brama Wyżynna" in text and "- S4: Przystań" in text  # within 3 stops
    assert "- S100:" not in text  # further along the line
    assert "- T8 (Line T8, every 12 min): S1 -2/3- S2 -2/3- S3 -2/3- S4 ..." in text
    assert "B199" in text.split("ALL ROUTES")[1] and "- B199 " not in text  # listed, not described
    assert "ALL ROUTES (id, minutes between buses): B199 30, T8 12, T10 10" in text


def test_a_named_line_is_shown_in_full() -> None:
    text = describe_excerpt(_network(extra_stops=20), "line 8 every 5 minutes")
    assert "S119" in text and "..." not in text.split("LINES:")[1].split("ALL ROUTES")[0].replace(
        '"...": the line continues', "")


def test_the_change_list_is_included() -> None:
    current = Scenario.model_validate({"changes": [
        {"type": "close_stop", "stop_id": "S6"},
        {"type": "change_frequency", "route_id": "T10", "headway_min": 5},
    ]}).changes
    text = describe_excerpt(NET, "undo the last one", current)
    assert "- S6: Łostowice Świętokrzyska" in text
    assert "- B199 (Line B199, every 30 min): " in text  # the line through S6
    assert "- T10 (Line T10, every 10 min): S7 >1> S8" in text  # used by a change: in full


def test_too_vague_requests_list_no_stations() -> None:
    many = dict(NAMES) | {f"S{100 + i}": f"Zajezdnia {i}" for i in range(20)}
    graph = build_graph([Stop(id=s, name=n, lat=0, lon=0, activity=1) for s, n in many.items()], [], [])
    assert "matched too many stops" in describe_excerpt(graph, "zajezdnia")


def test_size_decides_the_description(monkeypatch: pytest.MonkeyPatch) -> None:
    assert describe_network(NET).startswith("STOPS (id: name):")  # small: every link
    monkeypatch.setattr(ai_service, "COMPACT_NETWORK_CHARS", 10)
    assert describe_network(NET) == describe_lines(NET)
    monkeypatch.setattr(ai_service, "EXCERPT_NETWORK_CHARS", 10)
    assert describe_network(NET, "close Brama Wyżynna").startswith("NETWORK EXCERPT")


class _FakeModel:
    def __init__(self, answer: dict[str, Any]) -> None:
        self.answer = json.dumps({"remove_numbers": [], "replace": [], **answer})
        self.prompts: list[str] = []

    def complete_json(self, system_prompt: str, user_text: str, schema: dict) -> str:
        self.prompts.append(system_prompt)
        return self.answer


def test_interpret_sends_the_excerpt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_service, "COMPACT_NETWORK_CHARS", 10)
    monkeypatch.setattr(ai_service, "EXCERPT_NETWORK_CHARS", 10)
    model = _FakeModel({"status": "ok", "changes": [{"type": "close_stop", "stop_id": "S1"}], "message": "Closed."})
    result = interpret("zamknij Bramę Wyżynną", NET, model)
    assert result.status == "ok"
    assert "NETWORK EXCERPT" in model.prompts[0] and "- S1: Brama Wyżynna" in model.prompts[0]
    assert "- S6:" not in model.prompts[0]
    # A stop outside the excerpt is still checked against the whole network.
    model = _FakeModel({"status": "ok", "changes": [{"type": "close_stop", "stop_id": "S6"}], "message": "Closed."})
    assert interpret("zamknij Bramę Wyżynną", NET, model).status == "ok"


def test_build_system_prompt_without_text_keeps_small_networks_unchanged() -> None:
    assert build_system_prompt(NET) == build_system_prompt(NET, (), "anything")
