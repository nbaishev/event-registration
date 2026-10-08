"""Authorize with a short session; streaming only retains primitive event IDs."""

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from app.auth.service import current_user
from app.common.clock import Clock, get_clock
from app.common.config import Settings, get_settings
from app.common.errors import AppError
from app.db.session import get_engine
from app.events.broadcaster import StatsBroadcaster
from app.events.models import EventStatus
from app.events.service import get_owned_event

HEARTBEAT_SECONDS = 15


def authorize_stats_stream(
    event_id: UUID,
    request: Request,
    clock: Annotated[Clock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UUID:
    try:
        with Session(get_engine()) as session:
            user_id = current_user(
                session, clock, settings, request.cookies.get("access_token")
            ).id
            event = get_owned_event(session, user_id, event_id)
            if event.status == EventStatus.DRAFT:
                raise AppError(409, "EVENT_NOT_PUBLISHED", "Event is not published.")
            return event_id
    except SQLAlchemyError:
        raise AppError(503, "SERVICE_UNAVAILABLE", "Database is unavailable.") from None


async def stats_frames(
    broadcaster: StatsBroadcaster, queue: asyncio.Queue[None]
) -> AsyncIterator[str]:
    while not broadcaster.closed:
        try:
            await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
        except TimeoutError:
            yield ": heartbeat\n\n"
        else:
            if broadcaster.closed:
                break
            yield "event: stats_changed\ndata: {}\n\n"


class StatsStreamResponse(StreamingResponse):
    def __init__(self, broadcaster: StatsBroadcaster, event_id: UUID) -> None:
        self.broadcaster = broadcaster
        self.event_id = event_id
        self.queue = broadcaster.subscribe(event_id)
        super().__init__(
            stats_frames(broadcaster, self.queue),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store"},
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Also covers cancellation before the body iterator starts.
            self.broadcaster.unsubscribe(self.event_id, self.queue)
