from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session


def register(client: TestClient, email: str, password: str = " a long password "):
    token = client.get("/api/auth/csrf").json()["csrf_token"]
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )


def test_register_response_and_persisted_hash(
    auth_client: TestClient, auth_database: Engine
) -> None:
    from app.auth.models import User
    from app.auth.passwords import verify_password

    response = register(auth_client, "  Alice@EXAMPLE.COM  ")
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "email", "created_at", "updated_at"}
    UUID(body["id"])
    assert body["email"] == "alice@example.com"
    assert body["created_at"] == body["updated_at"] == "2026-10-04T12:00:00Z"
    assert "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    with Session(auth_database) as session:
        user = session.scalar(select(User))
        assert user is not None
        assert user.password_hash.startswith("$argon2id$")
        assert verify_password(" a long password ", user.password_hash)
        assert user.password_hash not in response.text
    assert " a long password " not in response.text


def test_duplicate_normalized_email_rollback_and_next_registration(
    auth_client: TestClient, auth_database: Engine
) -> None:
    assert register(auth_client, "alice@example.com").status_code == 201
    response = register(auth_client, " ALICE@EXAMPLE.COM ")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"
    assert response.json()["error"]["details"] == {}
    assert response.headers["cache-control"] == "no-store"
    assert register(auth_client, "bob@example.com").status_code == 201
    with auth_database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM users")) == 2


def test_concurrent_normalized_duplicate(
    auth_client: TestClient, auth_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.auth import repository

    barrier = Barrier(2, timeout=10)
    insert = repository.insert_user

    def synchronized_insert(session, user):
        barrier.wait()
        return insert(session, user)

    monkeypatch.setattr(repository, "insert_user", synchronized_insert)
    token = auth_client.get("/api/auth/csrf").json()["csrf_token"]

    def submit(email: str):
        return auth_client.post(
            "/api/auth/register",
            json={"email": email, "password": "long password!"},
            headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, [" Alice@example.com ", "ALICE@EXAMPLE.COM"]))
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert (
        next(r for r in responses if r.status_code == 409).json()["error"]["code"]
        == "EMAIL_ALREADY_REGISTERED"
    )
    with auth_database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM users")) == 1


@pytest.mark.parametrize(
    "length,status", [(11, 422), (12, 201), (128, 201), (129, 422)]
)
def test_password_api_boundaries_and_safe_errors(
    auth_client: TestClient, length: int, status: int
) -> None:
    response = register(auth_client, "alice@example.com", "я" * length)
    assert response.status_code == status
    if status == 422:
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert response.json()["error"]["details"] == {
            "fields": [{"field": "password", "code": "PASSWORD_LENGTH"}]
        }
        assert "я" * length not in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "body,details",
    [
        (
            {"email": "invalid", "password": "a long password"},
            {"fields": [{"field": "email", "code": "INVALID_EMAIL"}]},
        ),
        ({"email": "alice@example.com"}, {}),
        ({"email": "alice@example.com", "password": 123}, {}),
        ([], {}),
    ],
)
def test_safe_validation_envelope(
    auth_client: TestClient, body: object, details: dict
) -> None:
    token = auth_client.get("/api/auth/csrf").json()["csrf_token"]
    response = auth_client.post(
        "/api/auth/register",
        json=body,
        headers={"Origin": "http://localhost:8080", "X-CSRF-Token": token},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["details"] == details
    assert response.headers["cache-control"] == "no-store"


def test_csrf_invalid_has_no_db_mutation(
    auth_client: TestClient, auth_database: Engine
) -> None:
    response = auth_client.post(
        "/api/auth/register", content="{", headers={"Origin": "null"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_INVALID"
    with auth_database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM users")) == 0
