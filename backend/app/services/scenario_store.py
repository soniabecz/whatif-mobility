"""Save, list, read, overwrite and delete scenarios (Day 13).

Only change lists are stored. Each one is validated when saved and checked
against the CURRENT network whenever it is listed or read, because the network
may change after saving (a reseed, or later real data).
"""

import json
from datetime import UTC, datetime

import networkx as nx
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import SavedScenario
from app.schemas.saved_scenario import SavedScenarioIn, SavedScenarioInfo, SavedScenarioOut
from app.schemas.scenario import Scenario, ScenarioChange
from app.services.simulation_service import ScenarioError, apply_scenario

_CHANGES = TypeAdapter(list[ScenarioChange])


class ScenarioNotFoundError(LookupError):
    pass


class ScenarioNameTakenError(ValueError):
    pass


def _check_fits(baseline: nx.DiGraph, changes: list[ScenarioChange]) -> None:
    """Raise ScenarioError if the changes do not apply to the network (dry run)."""
    apply_scenario(baseline, Scenario(changes=changes))


def _utc(moment: datetime) -> datetime:
    """SQLite returns naive datetimes; they were stored in UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _read(row: SavedScenario, baseline: nx.DiGraph) -> SavedScenarioOut:
    try:
        changes = _CHANGES.validate_python(json.loads(row.changes_json))
        problem: str | None = None
        try:
            _check_fits(baseline, changes)
        except ScenarioError as error:
            problem = f"No longer fits the network: {error}"
        except ValidationError:  # e.g. an empty list
            problem = "The stored change list is not valid"
    except (json.JSONDecodeError, ValidationError):
        changes, problem = [], "Stored in a format this version cannot read"
    return SavedScenarioOut(
        id=row.id,
        name=row.name,
        change_count=len(changes),
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        fits=problem is None,
        problem=problem,
        changes=changes,
    )


def _dump(changes: list[ScenarioChange]) -> str:
    return json.dumps(_CHANGES.dump_python(changes, mode="json"))


def _get_row(db: Session, scenario_id: int) -> SavedScenario:
    row = db.get(SavedScenario, scenario_id)
    if row is None:
        raise ScenarioNotFoundError(f"No saved scenario with id {scenario_id}")
    return row


def _commit(db: Session, name: str) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise ScenarioNameTakenError(f"A scenario called '{name}' is already saved") from error


def list_scenarios(db: Session, baseline: nx.DiGraph) -> list[SavedScenarioInfo]:
    """Newest first (by last update), each checked against the current network."""
    rows = db.scalars(select(SavedScenario).order_by(SavedScenario.updated_at.desc(), SavedScenario.id.desc()))
    return [SavedScenarioInfo(**_read(row, baseline).model_dump(exclude={"changes"})) for row in rows]


def get_scenario(db: Session, baseline: nx.DiGraph, scenario_id: int) -> SavedScenarioOut:
    return _read(_get_row(db, scenario_id), baseline)


def create_scenario(db: Session, baseline: nx.DiGraph, data: SavedScenarioIn) -> SavedScenarioOut:
    """Raises ScenarioError (does not fit) or ScenarioNameTakenError."""
    _check_fits(baseline, data.changes)
    row = SavedScenario(name=data.name, changes_json=_dump(data.changes))
    db.add(row)
    _commit(db, data.name)
    return _read(row, baseline)


def update_scenario(
    db: Session, baseline: nx.DiGraph, scenario_id: int, data: SavedScenarioIn
) -> SavedScenarioOut:
    """Rename and/or overwrite the changes."""
    row = _get_row(db, scenario_id)
    _check_fits(baseline, data.changes)
    row.name = data.name
    row.changes_json = _dump(data.changes)
    _commit(db, data.name)
    return _read(row, baseline)


def delete_scenario(db: Session, scenario_id: int) -> None:
    db.delete(_get_row(db, scenario_id))
    db.commit()
