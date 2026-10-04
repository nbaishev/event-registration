from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.common.clock import FixedClock, SystemClock


def test_system_clock_returns_aware_utc() -> None:
    value = SystemClock().now()
    assert value.tzinfo == UTC


def test_fixed_clock_normalizes_aware_time_to_utc() -> None:
    clock = FixedClock(datetime(2026, 10, 4, 18, tzinfo=timezone(timedelta(hours=6))))
    assert clock.now() == datetime(2026, 10, 4, 12, tzinfo=UTC)
    assert clock.now().tzinfo == UTC


def test_fixed_clock_rejects_naive_time() -> None:
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 10, 4, 12))
