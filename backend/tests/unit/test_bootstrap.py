from pathlib import Path

from scripts.bootstrap import ensure_env


def test_bootstrap_creates_env_without_overwriting_existing_config(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env.example").write_text("APP_PORT=8080\n")
    ensure_env(tmp_path)
    assert (tmp_path / ".env").read_text() == "APP_PORT=8080\n"
    (tmp_path / ".env").write_text("APP_PORT=9876\n")
    ensure_env(tmp_path)
    assert (tmp_path / ".env").read_text() == "APP_PORT=9876\n"
