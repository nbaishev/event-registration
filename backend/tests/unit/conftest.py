from collections.abc import Iterator

import pytest

from app.common.config import get_settings


@pytest.fixture(autouse=True)
def isolated_unit_origin(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Unit request tests must not depend on the developer's local Compose port.
    monkeypatch.setenv("APP_ORIGIN", "http://localhost:8080")
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()
