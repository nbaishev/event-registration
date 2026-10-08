from datetime import UTC, datetime

from app.events.models import Event
from app.notifications.rendering import render_ticket_email
from app.registrations.models import Registration


def test_ticket_plain_text_uses_event_timezone_and_safe_subject():
    event = Event(
        title="Конференция\r\nBcc: attacker@example.com",
        slug="conference",
        starts_at=datetime(2026, 10, 9, 10, tzinfo=UTC),
        ends_at=datetime(2026, 10, 9, 12, tzinfo=UTC),
        timezone="Asia/Bishkek",
    )
    mail = render_ticket_email(
        "guest@example.com",
        event,
        Registration(ticket_code="7K4P9Q2M8RTA"),
        "https://events.example.com",
    )
    assert mail.recipient == "guest@example.com"
    assert "\r" not in mail.subject and "\n" not in mail.subject
    assert event.title in mail.body
    assert "2026-10-09 16:00" in mail.body
    assert "2026-10-09 18:00" in mail.body
    assert "UTC+06:00" in mail.body and "Asia/Bishkek" in mail.body
    assert "7K4P-9Q2M-8RTA" in mail.body
    assert "https://events.example.com/events/conference" in mail.body


def test_rendering_uses_dst_offset_for_each_endpoint():
    event = Event(
        title="DST",
        slug="dst",
        timezone="Europe/Berlin",
        starts_at=datetime(2026, 10, 25, 0, 30, tzinfo=UTC),
        ends_at=datetime(2026, 10, 25, 2, 30, tzinfo=UTC),
    )
    mail = render_ticket_email(
        "a@example.com",
        event,
        Registration(ticket_code="23456789ABCD"),
        "https://example.com",
    )
    assert "UTC+02:00" in mail.body and "UTC+01:00" in mail.body
