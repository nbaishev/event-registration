import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.common.clock import SystemClock
from app.common.config import get_settings
from app.db.session import get_engine
from app.notifications.celery_app import celery_app
from app.notifications.repository import (
    find_confirmation_candidates,
    find_reminder_candidates,
)
from app.notifications.service import deliver_confirmation, deliver_reminder
from app.notifications.smtp import SmtpMailSender

logger = logging.getLogger(__name__)


class NotificationTaskFailure(Exception):
    """Safe worker-visible failure; never carries SMTP/DB exception text."""


@celery_app.task(
    name="notifications.scan_confirmation",
    max_retries=0,
    throws=(NotificationTaskFailure,),
)
def scan_confirmation() -> None:
    try:
        with Session(get_engine()) as session:
            candidates = find_confirmation_candidates(session, SystemClock().now())
        for event_id, registration_id in candidates:
            send_confirmation.delay(str(event_id), str(registration_id))
    except Exception:
        logger.error("confirmation scan failed")
        raise NotificationTaskFailure("confirmation scan failed") from None


@celery_app.task(
    name="notifications.send_confirmation",
    max_retries=0,
    throws=(NotificationTaskFailure,),
)
def send_confirmation(event_id: str, registration_id: str) -> bool:
    # Canonical IDs are the only payload and the only contextual failure data.
    event_uuid, registration_uuid = UUID(event_id), UUID(registration_id)
    try:
        config = get_settings()
        with Session(get_engine()) as session:
            return deliver_confirmation(
                session,
                SystemClock(),
                SmtpMailSender(config),
                event_uuid,
                registration_uuid,
                config.app_origin,
            )
    except Exception:
        logger.error(
            "confirmation delivery failed event_id=%s registration_id=%s",
            event_uuid,
            registration_uuid,
        )
        raise NotificationTaskFailure("confirmation delivery failed") from None


@celery_app.task(
    name="notifications.scan_reminder",
    max_retries=0,
    throws=(NotificationTaskFailure,),
)
def scan_reminder() -> None:
    try:
        with Session(get_engine()) as session:
            candidates = find_reminder_candidates(session, SystemClock().now())
        for event_id, registration_id in candidates:
            send_reminder.delay(str(event_id), str(registration_id))
    except Exception:
        logger.error("reminder scan failed")
        raise NotificationTaskFailure("reminder scan failed") from None


@celery_app.task(
    name="notifications.send_reminder",
    max_retries=0,
    throws=(NotificationTaskFailure,),
)
def send_reminder(event_id: str, registration_id: str) -> bool:
    # Canonical IDs are the only payload and the only contextual failure data.
    event_uuid, registration_uuid = UUID(event_id), UUID(registration_id)
    try:
        config = get_settings()
        with Session(get_engine()) as session:
            return deliver_reminder(
                session,
                SystemClock(),
                SmtpMailSender(config),
                event_uuid,
                registration_uuid,
                config.app_origin,
            )
    except Exception:
        logger.error(
            "reminder delivery failed event_id=%s registration_id=%s",
            event_uuid,
            registration_uuid,
        )
        raise NotificationTaskFailure("reminder delivery failed") from None
