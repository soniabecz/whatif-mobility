"""Network endpoints."""

from fastapi.testclient import TestClient

from app.seed.sample_network import ROUTES, STOPS


def test_list_stops(client: TestClient) -> None:
    response = client.get("/api/stops")

    assert response.status_code == 200
    stops = response.json()
    assert len(stops) == len(STOPS)
    central = next(s for s in stops if s["id"] == "CEN")
    assert central["name"] == "Central Station"
    assert set(central) == {"id", "name", "lat", "lon"}


def test_list_routes(client: TestClient) -> None:
    response = client.get("/api/routes")

    assert response.status_code == 200
    assert [r["id"] for r in response.json()] == [r.id for r in ROUTES]


def test_get_network(client: TestClient) -> None:
    response = client.get("/api/network")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"stops", "routes", "connections"}
    assert len(body["stops"]) == len(STOPS)
    assert len(body["routes"]) == len(ROUTES)
    assert {
        "route_id": "R4",
        "from_stop_id": "MKT",
        "to_stop_id": "CEN",
        "travel_time_min": 2.0,
    }.items() <= next(
        c for c in body["connections"]
        if c["route_id"] == "R4" and c["from_stop_id"] == "MKT"
    ).items()
