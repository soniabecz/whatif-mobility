"""Shared fixtures: an isolated in-memory database seeded with the sample network."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers tables)
from app.config import Settings, get_settings
from app.database import Base, get_db
from app.main import app
from app.seed.seed_db import seed_database


@pytest.fixture
def engine() -> Iterator[Engine]:
    # StaticPool keeps ONE connection, so the in-memory DB survives across
    # sessions (and the TestClient's worker thread) within a test.
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        seed_database(session)
        yield session


@pytest.fixture
def client(db: Session, session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    # Isolated settings (no .env): penalty 0 and no waiting keep the
    # hand-calculated API expectations of Days 3-7 valid; tests needing
    # other values override this.
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,  # type: ignore[call-arg]
        groq_api_key=None,
        transfer_penalty_min=0.0,
        include_waiting=False,
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
