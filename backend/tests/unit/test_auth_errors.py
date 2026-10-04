import logging
from collections.abc import Iterator
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.common.csrf import AuthSecurityMiddleware
from app.db.session import get_engine, get_session
from app.main import app


def test_unexpected_auth_error_has_safe_envelope_and_no_store(caplog) -> None:
    probe = FastAPI()
    probe.add_middleware(AuthSecurityMiddleware)

    @probe.get("/api/auth/probe")
    def fail() -> None:
        raise RuntimeError("sensitive-input-marker")

    with caplog.at_level(logging.ERROR):
        with TestClient(probe, raise_server_exceptions=False) as client:
            response = client.get("/api/auth/probe")
    assert response.status_code == 500
    assert response.headers.get("cache-control") == "no-store"
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.json()["error"]["details"] == {}
    assert "sensitive-input-marker" not in response.text + caplog.text


def test_database_write_failure_rolls_back_without_hash_in_response_or_logs(
    caplog,
) -> None:
    session = Mock(spec=Session)
    hashes: list[str] = []

    def fail_commit() -> None:
        user = session.add.call_args.args[0]
        hashes.append(user.password_hash)
        raise OperationalError(
            "INSERT INTO users VALUES (...)",
            {"password_hash": user.password_hash},
            RuntimeError(f"database-error-with-hash:{user.password_hash}"),
        )

    session.commit.side_effect = fail_commit

    def failed_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = failed_session
    try:
        with caplog.at_level(logging.ERROR):
            with TestClient(app, raise_server_exceptions=False) as client:
                token = client.get("/api/auth/csrf").json()["csrf_token"]
                response = client.post(
                    "/api/auth/register",
                    json={
                        "email": "alice@example.com",
                        "password": "synthetic-password-value",
                    },
                    headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
                )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
        assert response.headers["cache-control"] == "no-store"
        session.rollback.assert_called_once()
        assert len(hashes) == 1
        assert hashes[0] not in response.text + caplog.text
        assert "synthetic-password-value" not in response.text + caplog.text
    finally:
        app.dependency_overrides.clear()


def test_engine_hides_sql_parameters_in_exception_text() -> None:
    engine = get_engine()
    error = OperationalError(
        "INSERT INTO users VALUES (...)",
        {"password_hash": "synthetic-hash-marker"},
        RuntimeError("connection lost"),
        hide_parameters=engine.hide_parameters,
    )
    assert "synthetic-hash-marker" not in str(error)
