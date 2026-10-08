from datetime import datetime
from zoneinfo import ZoneInfo

from app.events.models import Event
from app.notifications.contracts import MailMessage
from app.registrations.models import Registration
from app.registrations.tickets import format_ticket_code


def _local_time(value: datetime, timezone: str) -> str:
    local = value.astimezone(ZoneInfo(timezone))
    offset = local.strftime("%z")
    return f"{local:%Y-%m-%d %H:%M} (UTC{offset[:3]}:{offset[3:]}, {timezone})"


def render_ticket_email(
    recipient: str, event: Event, registration: Registration, app_origin: str
) -> MailMessage:
    assert registration.ticket_code is not None
    return MailMessage(
        recipient=recipient,
        # Event title is untrusted text and belongs only in the MIME body.
        subject="Подтверждение регистрации — ваш билет",
        body=(
            f"Ваша регистрация подтверждена.\n\nМероприятие: {event.title}\n"
            f"Начало: {_local_time(event.starts_at, event.timezone)}\n"
            f"Окончание: {_local_time(event.ends_at, event.timezone)}\n"
            f"Код билета: {format_ticket_code(registration.ticket_code)}\n"
            f"Страница мероприятия: {app_origin}/events/{event.slug}\n"
        ),
    )
