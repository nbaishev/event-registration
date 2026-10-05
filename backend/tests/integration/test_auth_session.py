from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.clock import FixedClock
from app.common.config import get_settings
from app.main import app


def headers(client):
    token = client.get("/api/auth/csrf").json()["csrf_token"]
    return {"Origin": get_settings().app_origin, "X-CSRF-Token": token}


def register(client):
    response = client.post(
        "/api/auth/register",
        headers=headers(client),
        json={"email": "alice@example.com", "password": " a long password "},
    )
    assert response.status_code == 201
    return response.json()


def login(client, email=" ALICE@EXAMPLE.COM ", password=" a long password "):
    return client.post(
        "/api/auth/login",
        headers=headers(client),
        json={"email": email, "password": password},
    )


def cookie_headers(response):
    result = {}
    for value in response.headers.get_list("set-cookie"):
        parsed = SimpleCookie()
        parsed.load(value)
        result.update(parsed)
    return result


def test_login_returns_public_user_and_exact_host_only_cookie_contract(auth_client):
    user = register(auth_client)
    response = login(auth_client)
    assert response.status_code == 200
    assert response.json() == user
    assert response.headers["cache-control"] == "no-store"
    cookies = cookie_headers(response)
    assert set(cookies) == {"access_token", "refresh_token"}
    for name, path, ttl in [
        ("access_token", "/api/", "900"),
        ("refresh_token", "/api/auth/refresh", "2592000"),
    ]:
        cookie = cookies[name]
        assert cookie["path"] == path
        assert cookie["max-age"] == ttl
        assert cookie["httponly"] is True
        assert cookie["samesite"].lower() == "lax"
        assert cookie["domain"] == ""
        assert cookie["secure"] == ""
        assert cookie.value not in response.text
    assert " a long password " not in response.text
    assert auth_client.get("/api/auth/me").json() == user


def test_unknown_email_and_wrong_password_have_identical_safe_failure(auth_client):
    register(auth_client)
    failures = [
        login(auth_client, email="unknown@example.com"),
        login(auth_client, password="incorrect password"),
        login(auth_client, password="a long password"),
    ]
    for response in failures:
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"
        assert response.headers["cache-control"] == "no-store"
        assert "set-cookie" not in response.headers
        assert response.json()["error"]["details"] == {}
    assert len({response.text for response in failures}) == 1


@pytest.mark.parametrize(
    "body,details",
    [
        (
            {"email": "invalid", "password": " a long password "},
            {"fields": [{"field": "email", "code": "INVALID_EMAIL"}]},
        ),
        (
            {"email": "alice@example.com", "password": "short"},
            {"fields": [{"field": "password", "code": "PASSWORD_LENGTH"}]},
        ),
        (
            {"email": "alice@example.com", "password": "я" * 129},
            {"fields": [{"field": "password", "code": "PASSWORD_LENGTH"}]},
        ),
        ({"email": "alice@example.com", "password": 123}, {}),
        ({}, {}),
    ],
)
def test_login_uses_register_validation_contract(auth_client, body, details):
    response = auth_client.post(
        "/api/auth/login", headers=headers(auth_client), json=body
    )
    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "VALIDATION_ERROR",
        "message": "Invalid request.",
        "details": details,
    }
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize(
    "kind", ["missing", "tampered", "expired", "refresh", "unknown-user"]
)
def test_me_rejects_invalid_access_and_missing_user(auth_client, auth_database, kind):
    from app.auth.router import get_clock
    from app.auth.tokens import issue_tokens

    user = register(auth_client)
    response = login(auth_client)
    assert response.status_code == 200
    access = auth_client.cookies.get("access_token")
    if kind == "missing":
        auth_client.cookies.clear()
    elif kind == "tampered":
        auth_client.cookies.set(
            "access_token", "tampered", domain="testserver.local", path="/api/"
        )
    elif kind == "expired":
        app.dependency_overrides[get_clock] = lambda: FixedClock(
            datetime(2026, 10, 4, 12, tzinfo=UTC) + timedelta(seconds=900)
        )
    elif kind == "refresh":
        pair = issue_tokens(
            UUID(user["id"]),
            FixedClock(datetime(2026, 10, 4, 12, tzinfo=UTC)),
            get_settings(),
        )
        auth_client.cookies.set(
            "access_token", pair.refresh, domain="testserver.local", path="/api/"
        )
    else:
        with Session(auth_database) as session:
            session.execute(delete(User).where(User.id == UUID(user["id"])))
            session.commit()
    response = auth_client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
    assert response.headers["cache-control"] == "no-store"
    assert access not in response.text


def test_logout_deletes_original_paths_without_requiring_auth_and_retains_csrf(
    auth_client,
):
    register(auth_client)
    assert login(auth_client).status_code == 200
    guard = headers(auth_client)
    # Refresh path excludes /logout, yet the browser jar must still delete it.
    assert "refresh_token" not in auth_client.build_request(
        "POST", "/api/auth/logout"
    ).headers.get("cookie", "")
    for _ in range(2):
        response = auth_client.post("/api/auth/logout", headers=guard)
        assert response.status_code == 204
        assert response.content == b""
        assert response.headers["cache-control"] == "no-store"
        cookies = cookie_headers(response)
        for name, path in [
            ("access_token", "/api/"),
            ("refresh_token", "/api/auth/refresh"),
        ]:
            assert cookies[name]["path"] == path
            assert cookies[name]["max-age"] == "0"
            assert cookies[name]["expires"] == "Thu, 01 Jan 1970 00:00:00 GMT"
            assert cookies[name]["httponly"] is True
            assert cookies[name]["samesite"].lower() == "lax"
            assert cookies[name]["domain"] == ""
        assert auth_client.cookies.get("access_token") is None
        assert auth_client.cookies.get("refresh_token") is None
        assert auth_client.cookies.get("csrf_token") == guard["X-CSRF-Token"]
        assert auth_client.get("/api/auth/me").status_code == 401
    auth_client.cookies.set("access_token", "malformed", path="/api/")
    assert auth_client.post("/api/auth/logout", headers=guard).status_code == 204


@pytest.mark.parametrize("path", ["/api/auth/login", "/api/auth/logout"])
@pytest.mark.parametrize("failure", ["missing", "foreign-origin", "wrong-csrf"])
def test_csrf_failure_cannot_issue_or_remove_auth_cookies(auth_client, path, failure):
    register(auth_client)
    assert login(auth_client).status_code == 200
    guard = headers(auth_client)
    if failure == "missing":
        guard = {}
    elif failure == "foreign-origin":
        guard["Origin"] += ".evil.test"
    else:
        guard["X-CSRF-Token"] = "wrong"
    response = auth_client.post(path, headers=guard, content="{")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_INVALID"
    assert "set-cookie" not in response.headers
    assert auth_client.get("/api/auth/me").status_code == 200


def test_production_auth_cookies_and_deletion_are_secure(auth_database, monkeypatch):
    from app.db.session import get_session

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("APP_ORIGIN", "https://testserver")
    get_settings.cache_clear()

    def session():
        with Session(auth_database) as value:
            yield value

    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app, base_url="https://testserver") as client:
            register(client)
            for response in [
                login(client),
                client.post("/api/auth/logout", headers=headers(client)),
            ]:
                for cookie in cookie_headers(response).values():
                    assert cookie["secure"] is True
            assert client.get("/api/auth/me").status_code == 401
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
