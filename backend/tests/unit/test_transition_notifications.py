from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)


def notice():
    from app.notifications.transitions import TransitionNotice

    return TransitionNotice(
        kind="EVENT_RESCHEDULED",
        event_id=uuid4(),
        occurred_at=NOW,
        recipient="snapshot@example.com",
        title="Title\nBcc: untrusted",
        slug="conference",
        starts_at=NOW + timedelta(days=2),
        ends_at=NOW + timedelta(days=2, hours=2),
        timezone="Asia/Bishkek",
    )


def test_snapshot_roundtrip_and_render():
    from app.notifications.rendering import render_transition_email
    from app.notifications.transitions import TransitionNotice

    n = notice()
    restored = TransitionNotice.model_validate(n.model_dump(mode="json"))
    mail = render_transition_email(restored, "https://events.example.com")
    assert mail.recipient == "snapshot@example.com"
    assert "2026-10-11 18:00" in mail.body and "2026-10-11 20:00" in mail.body
    assert "UTC+06:00" in mail.body and "Asia/Bishkek" in mail.body
    assert "https://events.example.com/events/conference" in mail.body
    assert n.title in mail.body and "Bcc" not in mail.subject
    with pytest.raises(ValidationError):
        n.recipient = "changed@example.com"


def test_dispatch_continues_and_logs_no_payload(caplog):
    from app.notifications.transitions import dispatch_transition_notices

    notices = [notice(), notice()]
    attempted = []

    class Dispatcher:
        def enqueue(self, n):
            attempted.append(n)
            if len(attempted) == 1:
                raise RuntimeError("secret snapshot@example.com")

    dispatch_transition_notices(Dispatcher(), notices)
    assert attempted == notices
    assert str(notices[0].event_id) in caplog.text
    assert "snapshot@example.com" not in caplog.text and "secret" not in caplog.text


@pytest.mark.parametrize("kind", ["EVENT_RESCHEDULED", "EVENT_CANCELLED"])
def test_task_sends_snapshot_once_without_database(monkeypatch, caplog, kind):
    from types import SimpleNamespace

    from app.notifications import tasks

    messages = []
    monkeypatch.setattr(
        tasks, "get_settings", lambda: SimpleNamespace(app_origin="https://example.com")
    )

    class Sender:
        def send(self, message):
            messages.append(message)
            raise OSError("secret snapshot@example.com")

    monkeypatch.setattr(tasks, "SmtpMailSender", lambda _: Sender())
    monkeypatch.setattr(
        tasks, "get_engine", lambda: pytest.fail("Snapshot task must not read DB")
    )
    with pytest.raises(tasks.NotificationTaskFailure):
        tasks.send_transition_notice.run(
            notice().model_copy(update={"kind": kind}).model_dump(mode="json")
        )
    assert len(messages) == 1
    assert tasks.send_transition_notice.max_retries == 0
    assert "secret" not in caplog.text and "snapshot@example.com" not in caplog.text


@pytest.mark.parametrize("kind", ["EVENT_CANCELLED", "EVENT_RESCHEDULED"])
def test_transition_kind_snapshot_render(kind):
    from app.notifications.rendering import render_transition_email

    n = notice().model_copy(update={"kind": kind})
    mail = render_transition_email(n, "https://example.com")
    assert mail.subject == (
        "Мероприятие отменено"
        if kind == "EVENT_CANCELLED"
        else "Изменение расписания мероприятия"
    )
    assert "2026-10-11 18:00" in mail.body
    assert "https://example.com/events/conference" in mail.body
    assert n.title in mail.body and mail.recipient == n.recipient
