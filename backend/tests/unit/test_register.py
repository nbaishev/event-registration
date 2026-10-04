import pytest
from pydantic import ValidationError

from app.auth.passwords import hash_password, verify_password
from app.auth.schemas import RegisterRequest


def test_email_normalized_before_validation() -> None:
    request = RegisterRequest(
        email="  Alice@EXAMPLE.COM  ", password=" a long password "
    )
    assert request.email == "alice@example.com"
    assert request.password == " a long password "


@pytest.mark.parametrize("length", [12, 128])
def test_password_character_boundaries_accepted(length: int) -> None:
    request = RegisterRequest(email="alice@example.com", password="я" * length)
    assert request.password == "я" * length


@pytest.mark.parametrize("length", [11, 129])
def test_password_character_boundaries_rejected(length: int) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="alice@example.com", password="я" * length)


@pytest.mark.parametrize("email", ["invalid", "", "a@", "@example.com"])
def test_invalid_email_rejected(email: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email=email, password="a long password")


def test_argon2id_hash_verifies_exact_password_with_random_salt() -> None:
    password = " a long password "
    hashed = hash_password(password)
    assert hashed.startswith("$argon2id$")
    assert password not in hashed
    assert verify_password(password, hashed)
    assert not verify_password(password.strip(), hashed)
    assert not verify_password("incorrect password", hashed)
    assert not verify_password(password, "invalid-hash")
    assert hash_password(password) != hashed
