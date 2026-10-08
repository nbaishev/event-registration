from datetime import UTC, datetime, timedelta

import pytest

from app.events.models import Event, EventStatus
from app.notifications.service import confirmation_eligible
from app.registrations.models import Registration, RegistrationStatus

NOW = datetime(2026, 10, 8, tzinfo=UTC)


@pytest.mark.parametrize(
    "event_status,registration_status,sent,starts,ticket,want",
    [
        ("PUBLISHED", "CONFIRMED", None, NOW + timedelta(seconds=1), "CODE", True),
        ("DRAFT", "CONFIRMED", None, NOW + timedelta(seconds=1), "CODE", False),
        ("CANCELLED", "CONFIRMED", None, NOW + timedelta(seconds=1), "CODE", False),
        ("PUBLISHED", "WAITLIST", None, NOW + timedelta(seconds=1), None, False),
        ("PUBLISHED", "CANCELLED", None, NOW + timedelta(seconds=1), None, False),
        ("PUBLISHED", "CONFIRMED", NOW, NOW + timedelta(seconds=1), "CODE", False),
        ("PUBLISHED", "CONFIRMED", None, NOW, "CODE", False),
        ("PUBLISHED", "CONFIRMED", None, NOW - timedelta(seconds=1), "CODE", False),
        ("PUBLISHED", "CONFIRMED", None, NOW + timedelta(seconds=1), None, False),
    ],
)
def test_delivery_eligibility(
    event_status, registration_status, sent, starts, ticket, want
):
    event = Event(status=EventStatus(event_status), starts_at=starts)
    row = Registration(
        status=RegistrationStatus(registration_status),
        confirmation_email_sent_at=sent,
        ticket_code=ticket,
    )
    assert confirmation_eligible(event, row, NOW) is want


def test_beat_schedule_and_json_only():
    from app.notifications.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule["confirmation-scan"]
    assert schedule["schedule"] == 300.0
    assert schedule["task"] == "notifications.scan_confirmation"
    assert celery_app.conf.result_backend is None
    assert celery_app.conf.accept_content == ["json"]
    assert celery_app.conf.task_serializer == "json"


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
    monkeypatch.setattr(tasks, "find_confirmation_candidates", lambda s, now: [pair])
    payloads = []

    def enqueue(*args):
        assert closed
        payloads.append(args)

    monkeypatch.setattr(tasks.send_confirmation, "delay", enqueue)
    tasks.scan_confirmation.run()
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

    monkeypatch.setattr(tasks, "deliver_confirmation", fail)
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: type("Config", (), {"app_origin": "https://example.com"})(),
    )
    monkeypatch.setattr(tasks, "SmtpMailSender", lambda config: object())
    e, r = str(uuid4()), str(uuid4())
    with pytest.raises(tasks.NotificationTaskFailure) as error:
        tasks.send_confirmation.run(e, r)
    assert secret not in str(error.value) and secret not in caplog.text
    assert "confirmation" in caplog.text and e in caplog.text and r in caplog.text
    assert tasks.send_confirmation.max_retries == 0
