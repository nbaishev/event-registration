import os
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from alembic import command
from app.common.clock import FixedClock
from app.db.session import get_session
from app.main import app


@pytest.fixture
def auth_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    url = os.environ["TEST_DATABASE_URL"]
    monkeypatch.setenv("DATABASE_URL", url)
    from app.common.config import get_settings

    get_settings.cache_clear()
    engine = create_engine(url)
    config = Config("backend/alembic.ini")
    command.upgrade(config, "head")
    try:
        yield engine
    finally:
        command.downgrade(config, "base")
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
        engine.dispose()
        get_settings.cache_clear()


@pytest.fixture
def auth_client(auth_database: Engine) -> Iterator[TestClient]:
    from app.auth.router import get_clock

    def test_session() -> Iterator[Session]:
        with Session(auth_database) as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[get_clock] = lambda: FixedClock(
        datetime(2026, 10, 4, 12, tzinfo=UTC)
    )
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
