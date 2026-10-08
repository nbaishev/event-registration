from datetime import UTC, datetime, timedelta

import pytest

from app.events.models import Event
from app.notifications import service
from app.registrations.models import Registration

NOW = datetime(2026, 10, 8, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "change,want",
    [
        ("eligible", True),
        ("before_window", False),
        ("inside_window", True),
        ("started", False),
        ("past", False),
        ("late_confirmation", False),
        ("late_schedule", False),
        ("draft", False),
        ("cancelled_event", False),
        ("waitlist", False),
        ("cancelled_registration", False),
        ("sent", False),
        ("confirmation_sent", True),
    ],
)
def test_reminder_eligibility_boundaries(change, want):
    event = Event(
        status="PUBLISHED", starts_at=NOW + timedelta(hours=24), schedule_updated_at=NOW
    )
    row = Registration(status="CONFIRMED", confirmed_at=NOW, reminder_sent_at=None)
    now = NOW
    if change == "before_window":
        now -= timedelta(microseconds=1)
    if change == "inside_window":
        now += timedelta(microseconds=1)
    if change == "started":
        now = event.starts_at
    if change == "past":
        now = event.starts_at + timedelta(microseconds=1)
    if change == "late_confirmation":
        row.confirmed_at += timedelta(microseconds=1)
    if change == "late_schedule":
        event.schedule_updated_at += timedelta(microseconds=1)
    if change == "draft":
        event.status = "DRAFT"
    if change == "cancelled_event":
        event.status = "CANCELLED"
    if change == "waitlist":
        row.status = "WAITLIST"
    if change == "cancelled_registration":
        row.status = "CANCELLED"
    if change == "sent":
        row.reminder_sent_at = NOW
    if change == "confirmation_sent":
        row.confirmation_email_sent_at = NOW
    assert service.reminder_eligible(event, row, now) is want


def test_reminder_beat_schedule():
    from app.notifications.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule["reminder-scan"]
    assert schedule == {"task": "notifications.scan_reminder", "schedule": 300.0}
    assert celery_app.conf.result_backend is None


def test_scanner_closes_session_before_enqueue(monkeypatch):
    from contextlib import contextmanager
    from uuid import uuid4

    from app.notifications import tasks

    pair = (uuid4(), uuid4())
    closed = False

    @contextmanager
    def session(engine):
        nonlocal closed
        yield object()
        closed = True

    monkeypatch.setattr(tasks, "Session", session)
    monkeypatch.setattr(tasks, "get_engine", lambda: object())
    monkeypatch.setattr(tasks, "find_reminder_candidates", lambda s, now: [pair])
    payloads = []

    def enqueue(*args):
        assert closed
        payloads.append(args)

    monkeypatch.setattr(tasks.send_reminder, "delay", enqueue)
    tasks.scan_reminder.run()
    assert payloads == [(str(pair[0]), str(pair[1]))]


def test_failure_logs_only_ids_and_no_automatic_retry(monkeypatch, caplog):
    from contextlib import contextmanager
    from uuid import uuid4

    from app.notifications import tasks

    @contextmanager
    def session(engine):
        yield object()

    monkeypatch.setattr(tasks, "Session", session)
    monkeypatch.setattr(tasks, "get_engine", lambda: object())
    secret = "recipient@example.com ticket secret-password body"

    def fail(*a, **kw):
        raise RuntimeError(secret)

    monkeypatch.setattr(tasks, "deliver_reminder", fail)
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: type("Config", (), {"app_origin": "https://example.com"})(),
    )
    monkeypatch.setattr(tasks, "SmtpMailSender", lambda config: object())
    e, r = str(uuid4()), str(uuid4())
    with pytest.raises(tasks.NotificationTaskFailure) as error:
        tasks.send_reminder.run(e, r)
    assert secret not in str(error.value) and secret not in caplog.text
    assert "reminder" in caplog.text and e in caplog.text and r in caplog.text
    assert tasks.send_reminder.max_retries == 0
