import base64
import hashlib
import hmac
import importlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest

from app.common.clock import FixedClock
from app.common.config import Settings
from app.common.errors import AppError

USER_ID = UUID("00000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)
SECRET = secrets.token_hex(32)


@pytest.fixture
def tokens():
    return importlib.import_module("app.auth.tokens")


@pytest.fixture
def settings():
    return Settings(_env_file=None, jwt_secret=SECRET)


def claims():
    return dict(
        sub=str(USER_ID),
        iat=1791115200,
        exp=1791116100,
        iss="event-registration",
        aud="event-registration-api",
        token_type="access",
    )


def test_issue_signed_typed_tokens_without_private_user_data(tokens, settings):
    pair = tokens.issue_tokens(USER_ID, FixedClock(NOW), settings)
    assert SECRET not in repr(pair)
    for token, kind, expiry in [
        (pair.access, "access", 1791116100),
        (pair.refresh, "refresh", 1793707200),
    ]:
        decoded = jwt.decode(
            token,
            SECRET,
            algorithms=["HS256"],
            audience="event-registration-api",
            issuer="event-registration",
            options={"verify_exp": False, "verify_iat": False},
        )
        assert decoded == claims() | {"token_type": kind, "exp": expiry}
        assert tokens.verify_token(token, kind, FixedClock(NOW), settings) == USER_ID


@pytest.mark.parametrize("offset,accepted", [(899, True), (900, False), (901, False)])
def test_access_expiry_uses_injected_clock_without_leeway(
    tokens, settings, offset, accepted
):
    token = tokens.issue_tokens(USER_ID, FixedClock(NOW), settings).access
    clock = FixedClock(NOW + timedelta(seconds=offset))
    if accepted:
        assert tokens.verify_token(token, "access", clock, settings) == USER_ID
    else:
        with pytest.raises(AppError) as caught:
            tokens.verify_token(token, "access", clock, settings)
        assert caught.value.code == "AUTH_REQUIRED"
        assert caught.value.status == 401


@pytest.mark.parametrize("field", ["sub", "iat", "exp", "iss", "aud", "token_type"])
def test_missing_claims_rejected(tokens, settings, field):
    payload = claims()
    del payload[field]
    token = jwt.encode(payload, SECRET, algorithm="HS256")
    with pytest.raises(AppError):
        tokens.verify_token(token, "access", FixedClock(NOW), settings)


@pytest.mark.parametrize(
    "patch",
    [
        {"sub": "invalid"},
        {"sub": 12},
        {"iat": True},
        {"iat": "1791115200"},
        {"iat": 1791115200.0},
        {"iat": 1791115201},
        {"exp": True},
        {"exp": "1791116100"},
        {"exp": 1791116100.0},
        {"exp": 1791115200},
        {"exp": 1791115199},
        {"iss": "foreign"},
        {"iss": ["event-registration"]},
        {"aud": "foreign"},
        {"aud": ["event-registration-api"]},
        {"token_type": "refresh"},
        {"token_type": 1},
    ],
)
def test_invalid_claims_rejected(tokens, settings, patch):
    # Sign adversarial claims independently; PyJWT.encode rejects malformed issuer.
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=")

    message = encode({"alg": "HS256", "typ": "JWT"}) + b"." + encode(claims() | patch)
    signature = base64.urlsafe_b64encode(
        hmac.digest(SECRET.encode(), message, hashlib.sha256)
    ).rstrip(b"=")
    token = (message + b"." + signature).decode()
    with pytest.raises(AppError) as caught:
        tokens.verify_token(token, "access", FixedClock(NOW), settings)
    assert caught.value.code == "AUTH_REQUIRED"


@pytest.mark.parametrize(
    "kind", ["tampered", "wrong-key", "HS384", "none", "malformed"]
)
def test_crypto_verification_remains_enabled_under_fake_clock(tokens, settings, kind):
    token = jwt.encode(claims(), SECRET, algorithm="HS256")
    if kind == "tampered":
        header, _, signature = token.split(".")
        forged_payload = jwt.encode(
            claims() | {"sub": str(UUID(int=2))}, SECRET, algorithm="HS256"
        ).split(".")[1]
        token = ".".join([header, forged_payload, signature])
    elif kind == "wrong-key":
        token = jwt.encode(claims(), secrets.token_hex(32), algorithm="HS256")
    elif kind in {"HS384", "none"}:
        token = jwt.encode(claims(), None if kind == "none" else SECRET, algorithm=kind)
    else:
        token = "malformed"
    with pytest.raises(AppError):
        tokens.verify_token(token, "access", FixedClock(NOW), settings)


def test_refresh_cannot_authorize_access(tokens, settings):
    token = tokens.issue_tokens(USER_ID, FixedClock(NOW), settings).refresh
    with pytest.raises(AppError):
        tokens.verify_token(token, "access", FixedClock(NOW), settings)
