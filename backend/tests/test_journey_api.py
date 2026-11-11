"""POST /api/journeys."""

from fastapi.testclient import TestClient


def test_journey_before_and_after(client: TestClient) -> None:
    response = client.post("/api/journeys", json={
        "origin_id": "EST",
        "destination_id": "MKT",
        "changes": [{"type": "close_stop", "stop_id": "CEN"}],
    })

    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["change_min"], body["reason"]) == ("slower", 3.0, None)
    assert body["before"]["travel_time_min"] == 11.0
    assert body["after"]["travel_time_min"] == 14.0
    assert body["after"]["legs"][-1] == {
        "route_id": "R4",
        "stop_ids": ["STD", "CEN", "MKT"],
        "travel_time_min": 6.0,
        "passes_closed_stop_ids": ["CEN"],
    }


def test_journey_without_changes_is_unchanged(client: TestClient) -> None:
    response = client.post("/api/journeys", json={"origin_id": "NTH", "destination_id": "AIR"})

    assert response.status_code == 200
    assert response.json()["status"] == "unchanged"


def test_unknown_stop_returns_422(client: TestClient) -> None:
    response = client.post("/api/journeys", json={"origin_id": "XXX", "destination_id": "CEN"})

    assert response.status_code == 422
    assert response.json() == {"detail": "Unknown stop 'XXX'"}


def test_invalid_change_returns_422_with_message(client: TestClient) -> None:
    response = client.post("/api/journeys", json={
        "origin_id": "NTH",
        "destination_id": "STH",
        "changes": [{"type": "close_stop", "stop_id": "NOPE"}],
    })

    assert response.status_code == 422
    assert response.json() == {"detail": "Change 1 (close_stop): unknown stop 'NOPE'"}


def test_same_stop_twice_returns_422(client: TestClient) -> None:
    response = client.post("/api/journeys", json={"origin_id": "CEN", "destination_id": "CEN"})

    assert response.status_code == 422
