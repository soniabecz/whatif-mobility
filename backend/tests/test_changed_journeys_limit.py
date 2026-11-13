"""Large results (Day 14, step B2): a result lists the largest changed journeys;
the CSV from the backend has all of them; every figure uses all of them."""

import csv
import io
from typing import Any

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Connection, Route, Stop
from app.schemas.scenario import Scenario
from app.schemas.simulation import JourneyChange
from app.services.export_service import changed_journeys_csv
from app.services.network_service import build_graph, build_graph_from_db
from app.services.simulation_service import simulate, table_order


@pytest.fixture
def sample(db: Session) -> nx.DiGraph:
    return build_graph_from_db(db)


def _line(n: int) -> nx.DiGraph:
    """One two-way line through n stops (S00 - S01 - ...), 1 min apart."""
    stops = [Stop(id=f"S{i:02d}", name=f"Stop {i}", lat=0.0, lon=i / 100, activity=1) for i in range(n)]
    links = []
    for i in range(n - 1):
        links += [Connection(route_id="L", from_stop_id=f"S{i:02d}", to_stop_id=f"S{i + 1:02d}", travel_time_min=1),
                  Connection(route_id="L", from_stop_id=f"S{i + 1:02d}", to_stop_id=f"S{i:02d}", travel_time_min=1)]
    return build_graph(stops, links, [Route(id="L", name="Line", color="#000000", headway_min=10)])


def _scenario(*changes: dict[str, Any]) -> Scenario:
    return Scenario.model_validate({"changes": list(changes)})


def test_a_large_result_lists_the_largest_changes() -> None:
    line = _line(30)
    # Slowing the middle link changes 2 x 15 x 15 = 450 journeys.
    scenario = _scenario({"type": "change_travel_time", "from_stop_id": "S14", "to_stop_id": "S15",
                          "travel_time_min": 5})
    full = simulate(line, scenario, max_changed=None)
    capped = simulate(line, scenario, max_changed=100)
    assert (full.changed_journeys_total, capped.changed_journeys_total) == (450, 450)
    assert len(capped.changed_journeys) == 100  # +10 chart journeys: already among them here
    assert capped.summary == full.summary and capped.stop_impacts == full.stop_impacts
    # The same first rows as the table built from the full list.
    assert table_order(capped.changed_journeys) == table_order(full.changed_journeys)[:100]
    keys = [(j.origin_id, j.destination_id) for j in capped.changed_journeys]
    assert keys == sorted(keys)  # still listed by (origin, destination)


def test_the_chart_keeps_its_journeys_when_many_become_impossible() -> None:
    line = _line(30)
    # Cutting the middle link: 450 journeys impossible; slowing S00-S01: 58 slower.
    scenario = _scenario(
        {"type": "remove_connection", "from_stop_id": "S14", "to_stop_id": "S15"},
        {"type": "change_travel_time", "from_stop_id": "S00", "to_stop_id": "S01", "travel_time_min": 3},
    )
    capped = simulate(line, scenario, max_changed=100)
    statuses = [j.status for j in capped.changed_journeys]
    assert statuses.count("impossible") == 100 and statuses.count("slower") == 10
    assert capped.changed_journeys_total == 450 + 2 * 14


def test_small_results_are_unchanged(sample: nx.DiGraph) -> None:
    result = simulate(sample, _scenario({"type": "close_stop", "stop_id": "CEN"}))
    assert len(result.changed_journeys) == result.changed_journeys_total


def _journey(origin: str, destination: str, before: float, after: float | None, status: str) -> JourneyChange:
    change = None if after is None else round(after - before, 1)
    return JourneyChange(origin_id=origin, destination_id=destination, time_before_min=before,
                         time_after_min=after, change_min=change, status=status)  # type: ignore[arg-type]


def test_csv_format() -> None:
    journeys = [
        _journey("A", "B", 4.0, 5.5, "slower"),
        _journey("B", "C", 10.0, None, "impossible"),
        _journey("C", "A", 12.0, 3.0, "faster"),
    ]
    text = changed_journeys_csv(journeys, {"A": "Alpha", "B": 'Bridge "Old", East', "C": "Ćma"})
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    lines = text.split("\r\n")
    assert lines[0] == "origin_id,origin_name,destination_id,destination_name,status,time_before_min,time_after_min,change_min"
    assert lines[1] == 'B,"Bridge ""Old"", East",C,Ćma,impossible,10,,'  # impossible first; quoted
    assert lines[2] == "C,Ćma,A,Alpha,faster,12,3,-9"  # then the largest change; "12", not "12.0"
    assert lines[3] == 'A,Alpha,B,"Bridge ""Old"", East",slower,4,5.5,1.5'


def test_csv_endpoint_has_every_journey(client: TestClient) -> None:
    body = {"changes": [{"type": "close_stop", "stop_id": "CEN"}]}
    response = client.post("/api/simulations/csv", json=body)
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    result = client.post("/api/simulations", json=body).json()
    assert len(rows) == result["changed_journeys_total"]
    first = rows[0]
    expected = table_order([JourneyChange(**j) for j in result["changed_journeys"]])[0]
    assert (first["origin_id"], first["destination_id"]) == (expected.origin_id, expected.destination_id)
    bad = client.post("/api/simulations/csv", json={"changes": [{"type": "close_stop", "stop_id": "XYZ"}]})
    assert bad.status_code == 422
