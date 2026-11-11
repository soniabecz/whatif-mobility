"""POST /api/simulations."""

from fastapi.testclient import TestClient


def test_simulation_returns_metrics(client: TestClient) -> None:
    response = client.post(
        "/api/simulations",
        json={"changes": [{"type": "close_stop", "stop_id": "CEN"}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "scenario", "summary", "changed_journeys", "stop_impacts", "most_affected_stop_ids",
    }
    assert body["summary"]["total_journeys"] == 240
    assert body["summary"]["to_or_from_closed_stop"] == 30
    assert body["scenario"]["changes"][0] == {"type": "close_stop", "stop_id": "CEN"}


def test_simulation_does_not_change_stored_network(client: TestClient) -> None:
    before = client.get("/api/network").json()

    client.post(
        "/api/simulations",
        json={"changes": [{"type": "remove_connection",
                           "from_stop_id": "MKT", "to_stop_id": "CEN"}]},
    )

    assert client.get("/api/network").json() == before


def test_unknown_stop_returns_422_with_message(client: TestClient) -> None:
    response = client.post(
        "/api/simulations",
        json={"changes": [{"type": "close_stop", "stop_id": "XXX"}]},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Change 1 (close_stop): unknown stop 'XXX'"}


def test_malformed_scenario_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/simulations",
        json={"changes": [{"type": "change_travel_time", "from_stop_id": "MKT",
                           "to_stop_id": "CEN", "travel_time_min": 0}]},
    )

    assert response.status_code == 422
