"""Saved scenarios (Day 13): only change lists are stored, checked against the
current network on every read; results are never stored."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.models import Connection, SavedScenario, Stop

CLOSE_CEN = {"type": "close_stop", "stop_id": "CEN"}
SLOW = {"type": "change_travel_time", "from_stop_id": "RIV", "to_stop_id": "EST", "travel_time_min": 9,
        "both_directions": True}


def _save(client: TestClient, name: str = "Central closed", changes: list[Any] | None = None) -> Any:
    return client.post("/api/scenarios", json={"name": name, "changes": changes or [CLOSE_CEN]})


def test_save_read_list(client: TestClient) -> None:
    created = _save(client, "  Central closed  ")
    assert created.status_code == 201
    body = created.json()
    assert (body["name"], body["changes"], body["change_count"], body["fits"], body["problem"]) == (
        "Central closed", [CLOSE_CEN], 1, True, None)
    assert body["created_at"].endswith(("Z", "+00:00"))  # UTC, not a local time

    assert client.get(f"/api/scenarios/{body['id']}").json() == body
    _save(client, "Slow river", [SLOW, CLOSE_CEN])
    listing = client.get("/api/scenarios").json()
    assert [row["name"] for row in listing] == ["Slow river", "Central closed"]  # newest first
    assert "changes" not in listing[0] and listing[0]["change_count"] == 2


def test_only_changes_are_stored(client: TestClient, db: Session) -> None:
    _save(client)
    columns = {column["name"] for column in inspect(db.get_bind()).get_columns("saved_scenarios")}
    assert columns == {"id", "name", "changes_json", "created_at", "updated_at"}
    row = db.scalars(select(SavedScenario)).one()
    assert "slower" not in row.changes_json and "summary" not in row.changes_json


def test_overwrite_rename_and_delete(client: TestClient) -> None:
    scenario_id = _save(client).json()["id"]
    updated = client.put(f"/api/scenarios/{scenario_id}", json={"name": "Renamed", "changes": [SLOW]})
    assert updated.status_code == 200
    assert (updated.json()["name"], updated.json()["changes"]) == ("Renamed", [SLOW])
    assert client.delete(f"/api/scenarios/{scenario_id}").status_code == 204
    assert client.get(f"/api/scenarios/{scenario_id}").status_code == 404
    assert client.delete(f"/api/scenarios/{scenario_id}").status_code == 404
    assert client.put(f"/api/scenarios/{scenario_id}", json={"name": "x", "changes": [SLOW]}).status_code == 404


def test_names_are_unique(client: TestClient) -> None:
    _save(client)
    duplicate = _save(client, "Central closed", [SLOW])
    assert duplicate.status_code == 409 and "already saved" in duplicate.json()["detail"]
    other = _save(client, "Other", [SLOW]).json()["id"]
    renamed = client.put(f"/api/scenarios/{other}", json={"name": "Central closed", "changes": [SLOW]})
    assert renamed.status_code == 409
    assert client.get(f"/api/scenarios/{other}").json()["name"] == "Other"  # rolled back


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"name": "x", "changes": [{"type": "close_stop", "stop_id": "XYZ"}]}, 422),  # does not fit
        ({"name": "x", "changes": []}, 422),
        ({"name": " ", "changes": [CLOSE_CEN]}, 422),
        ({"name": "x", "changes": [CLOSE_CEN], "result": {}}, 422),  # results are never accepted
    ],
)
def test_invalid_scenarios_are_not_saved(client: TestClient, body: dict[str, Any], status: int) -> None:
    assert client.post("/api/scenarios", json=body).status_code == status
    assert client.get("/api/scenarios").json() == []


def test_a_scenario_that_no_longer_fits_is_flagged(client: TestClient, db: Session) -> None:
    scenario_id = _save(client, "Slow river", [SLOW]).json()["id"]
    # The network changes after saving: Riverside – East Gate no longer exists.
    for connection in db.scalars(select(Connection).where(Connection.from_stop_id.in_(["RIV", "EST"]),
                                                          Connection.to_stop_id.in_(["RIV", "EST"]))):
        db.delete(connection)
    db.commit()
    row = client.get("/api/scenarios").json()[0]
    assert (row["fits"], row["change_count"]) == (False, 1)
    assert row["problem"] == "No longer fits the network: Change 1 (change_travel_time): no connection from 'RIV' to 'EST'"
    assert client.get(f"/api/scenarios/{scenario_id}").json()["changes"] == [SLOW]  # still readable


def test_an_unreadable_stored_list_is_flagged(client: TestClient, db: Session) -> None:
    db.add(SavedScenario(name="Old", changes_json='[{"type": "teleport"}]'))
    db.commit()
    row = client.get("/api/scenarios").json()[0]
    assert (row["fits"], row["change_count"], row["problem"]) == (
        False, 0, "Stored in a format this version cannot read")


# --- Seeding never drops saved scenarios ---------------------------------------------------

def _run_seed(monkeypatch: pytest.MonkeyPatch, path: Path, *args: str) -> None:
    from app.seed import __main__ as seed_main

    engine = create_engine(f"sqlite:///{path}")
    monkeypatch.setattr(seed_main, "engine", engine)
    monkeypatch.setattr(seed_main, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr("sys.argv", ["seed", *args])
    seed_main.main()


def test_rebuilding_outdated_network_tables_keeps_saved_scenarios(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "whatif.db"
    _run_seed(monkeypatch, path)
    engine = create_engine(f"sqlite:///{path}")
    with Session(engine) as db:
        db.add(SavedScenario(name="Keep me", changes_json="[]"))
        db.commit()
    with engine.begin() as connection:  # simulate a model change in a network table
        connection.execute(text("ALTER TABLE stops ADD COLUMN legacy TEXT"))

    _run_seed(monkeypatch, path, "--if-empty")
    with Session(engine) as db:
        assert db.scalars(select(SavedScenario.name)).all() == ["Keep me"]
        assert db.scalars(select(Stop)).first() is not None  # network rebuilt and seeded
    assert "legacy" not in {c["name"] for c in inspect(engine).get_columns("stops")}


def test_an_outdated_saved_scenarios_table_stops_the_seed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "whatif.db"
    _run_seed(monkeypatch, path)
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE saved_scenarios ADD COLUMN legacy TEXT"))
    with pytest.raises(SystemExit, match="saved_scenarios.*not dropped automatically"):
        _run_seed(monkeypatch, path)
    assert "saved_scenarios" in inspect(engine).get_table_names()  # left as it was
