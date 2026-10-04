import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine(os.environ["TEST_DATABASE_URL"])

    def test_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(app) as http:
            yield http
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_health_contract(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_queries_real_postgresql(client: TestClient) -> None:
    response = client.get("/api/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_unavailable_database_is_safe_503(client: TestClient) -> None:
    engine = create_engine(
        "postgresql+psycopg://secret_user:secret_password@127.0.0.1:1/private_db",
        connect_args={"connect_timeout": 1},
    )

    def unavailable_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = unavailable_session
    try:
        response = client.get("/api/ready")
        assert response.status_code == 503
        assert response.json() == {
            "error": {
                "code": "SERVICE_UNAVAILABLE",
                "message": "Database is unavailable.",
                "details": {},
            }
        }
        assert "secret" not in response.text
        assert "private_db" not in response.text
    finally:
        engine.dispose()
