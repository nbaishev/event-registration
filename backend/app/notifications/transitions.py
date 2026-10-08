"""Immutable transition snapshots dispatched only after a successful commit."""

import logging
from typing import Literal, Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class TransitionNotice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["EVENT_RESCHEDULED", "EVENT_CANCELLED"]
    event_id: UUID
    occurred_at: AwareDatetime
    recipient: str
    title: str
    slug: str
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    timezone: str


class TransitionDispatcher(Protocol):
    def enqueue(self, notice: TransitionNotice) -> None: ...


class CeleryTransitionDispatcher:
    def enqueue(self, notice: TransitionNotice) -> None:
        from app.notifications.tasks import send_transition_notice

        send_transition_notice.apply_async(
            args=[notice.model_dump(mode="json")],
            argsrepr="(<transition snapshot>,)",
        )


def get_transition_dispatcher() -> TransitionDispatcher:
    return CeleryTransitionDispatcher()


def dispatch_transition_notices(
    dispatcher: TransitionDispatcher | None, notices: list[TransitionNotice]
) -> None:
    if dispatcher is None:
        return
    for notice in notices:
        try:
            dispatcher.enqueue(notice)
        except Exception:
            logger.error(
                "transition enqueue failed kind=%s event_id=%s",
                notice.kind,
                notice.event_id,
            )
