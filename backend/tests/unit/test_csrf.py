from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.common.config import Settings, get_settings
from app.main import app


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "cookie,header,origin",
    [
        (None, "token", "http://localhost:8080"),
        ("token", None, "http://localhost:8080"),
        ("token", "wrong", "http://localhost:8080"),
        ("", "", "http://localhost:8080"),
        ("token", "token", None),
        ("token", "token", "null"),
        ("token", "token", "http://localhost:8080.evil.test"),
        ("token", "token", "http://localhost:8081"),
        ("token", "token", "https://localhost:8080"),
        ("token", "token", "http://localhost:8080/"),
        ("token", "token", "http://localhost:8080/path"),
        ("token", "token", "https://foreign.example"),
        ("malformed%token", "token", "http://localhost:8080"),
    ],
)
def test_unsafe_guard_precedes_body_validation_and_use_case(
    method: str,
    cookie: str | None,
    header: str | None,
    origin: str | None,
) -> None:
    from app.common.csrf import AuthSecurityMiddleware

    spy = Mock()
    probe = FastAPI()
    probe.add_middleware(AuthSecurityMiddleware)

    @probe.api_route("/api/auth/probe", methods=["POST", "PUT", "PATCH", "DELETE"])
    def mutate(body: dict[str, str]) -> dict[str, str]:
        spy(body)
        return {"status": "mutated"}

    headers = {"Referer": "http://localhost:8080/register"}
    if origin is not None:
        headers["Origin"] = origin
    if header is not None:
        headers["X-CSRF-Token"] = header
    with TestClient(probe) as client:
        if cookie is not None:
            client.cookies.set("csrf_token", cookie)
        response = client.request(
            method, "/api/auth/probe", headers=headers, content="{"
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_INVALID"
    assert response.headers["cache-control"] == "no-store"
    spy.assert_not_called()


def test_valid_guard_allows_use_case() -> None:
    from app.common.csrf import AuthSecurityMiddleware

    probe = FastAPI()
    probe.add_middleware(AuthSecurityMiddleware)

    @probe.post("/api/auth/probe")
    def mutate(body: dict[str, str]) -> dict[str, str]:
        return body

    with TestClient(probe) as client:
        client.cookies.set("csrf_token", "token")
        response = client.post(
            "/api/auth/probe",
            json={"value": "saved"},
            headers={
                "Origin": "http://localhost:8080",
                "X-CSRF-Token": "token",
            },
        )
    assert response.status_code == 200
    assert response.json() == {"value": "saved"}


@pytest.mark.parametrize(
    "environment,secure", [("development", False), ("production", True)]
)
def test_csrf_cookie_contract_and_fresh_random_token(
    environment: str,
    secure: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", environment)
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            response = client.get("/api/auth/csrf")
            assert response.status_code == 200
            token = response.json()["csrf_token"]
            assert len(token) >= 32
            assert client.cookies.get("csrf_token") == token
            cookie = response.headers["set-cookie"].lower()
            assert "path=/" in cookie and "samesite=lax" in cookie
            for absent in ["httponly", "domain=", "max-age=", "expires="]:
                assert absent not in cookie
            assert ("secure" in cookie) is secure
            assert response.headers["cache-control"] == "no-store"
            assert client.get("/api/auth/csrf").json()["csrf_token"] != token
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:8080/",
        "http://localhost:8080/path",
        "http://localhost:8080?x=1",
        "http://localhost:8080#fragment",
        "http://user@localhost:8080",
        "null",
    ],
)
def test_configured_origin_rejects_paths_and_non_origins(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_origin=origin)


@pytest.mark.parametrize(
    "configured,browser_origin",
    [
        ("https://Example.com", "https://example.com"),
        ("http://Example.com:80", "http://example.com"),
        ("https://Example.com:443", "https://example.com"),
        ("https://Example.com:8443", "https://example.com:8443"),
    ],
)
def test_guard_accepts_browser_origin_from_canonical_settings(
    configured: str,
    browser_origin: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.common.csrf import AuthSecurityMiddleware

    monkeypatch.setenv("APP_ORIGIN", configured)
    get_settings.cache_clear()
    probe = FastAPI()
    probe.add_middleware(AuthSecurityMiddleware)

    @probe.post("/api/auth/probe")
    def mutate(body: dict[str, str]) -> dict[str, str]:
        return body

    try:
        with TestClient(probe) as client:
            client.cookies.set("csrf_token", "token")
            response = client.post(
                "/api/auth/probe",
                json={"value": "saved"},
                headers={
                    "Origin": browser_origin,
                    "X-CSRF-Token": "token",
                },
            )
        assert response.status_code == 200
        assert response.json() == {"value": "saved"}
    finally:
        get_settings.cache_clear()
