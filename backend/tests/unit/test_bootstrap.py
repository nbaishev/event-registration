from pathlib import Path

import pytest
from scripts.bootstrap import ensure_env


def secret(path):
    return next(
        line.partition("=")[2]
        for line in path.read_text().splitlines()
        if line.startswith("JWT_SECRET=")
    )


def test_bootstrap_generates_secret_once_preserving_existing_config(
    tmp_path: Path, capsys
):
    (tmp_path / ".env.example").write_text("APP_PORT=8080\nJWT_SECRET=\n")
    ensure_env(tmp_path)
    env = tmp_path / ".env"
    first = secret(env)
    assert len(bytes.fromhex(first)) >= 32
    assert env.stat().st_mode & 0o777 == 0o600
    assert "APP_PORT=8080\n" in env.read_text()
    assert first not in capsys.readouterr().out
    env.write_text(env.read_text().replace("8080", "9876"))
    contents = env.read_text()
    ensure_env(tmp_path)
    assert env.read_text() == contents
    assert secret(env) == first


def test_bootstrap_adds_missing_secret_to_existing_local_env(tmp_path):
    (tmp_path / ".env").write_text("APP_PORT=9876\n")
    ensure_env(tmp_path)
    assert (tmp_path / ".env").read_text().startswith("APP_PORT=9876\n")
    assert len(bytes.fromhex(secret(tmp_path / ".env"))) >= 32


def test_bootstrap_requires_explicit_production_secret(tmp_path, monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    (tmp_path / ".env").write_text("ENVIRONMENT=production\nJWT_SECRET=\n")
    original = (tmp_path / ".env").read_text()
    with pytest.raises(ValueError, match="explicit JWT_SECRET"):
        ensure_env(tmp_path)
    assert (tmp_path / ".env").read_text() == original
