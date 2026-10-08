"""Best-effort, event-scoped notifications owned by one application lifespan."""

import asyncio
import logging
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

logger = logging.getLogger(__name__)


class StatsBroadcaster:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: dict[UUID, set[asyncio.Queue[None]]] = {}

    @property
    def closed(self) -> bool:
        return self._loop is None

    def startup(self) -> None:
        self._loop = asyncio.get_running_loop()

    def subscribe(self, event_id: UUID) -> asyncio.Queue[None]:
        if self.closed:
            raise RuntimeError("Broadcaster is closed")
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        self._subscribers.setdefault(event_id, set()).add(queue)
        return queue

    def unsubscribe(self, event_id: UUID, queue: asyncio.Queue[None]) -> None:
        subscribers = self._subscribers.get(event_id)
        if subscribers is not None:
            subscribers.discard(queue)
            if not subscribers:
                del self._subscribers[event_id]

    def publish(self, event_id: UUID) -> None:
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._deliver, event_id)

    def _deliver(self, event_id: UUID) -> None:
        for queue in self._subscribers.get(event_id, ()):
            if queue.empty():
                queue.put_nowait(None)

    def shutdown(self) -> None:
        self._loop = None
        for subscribers in self._subscribers.values():
            for queue in subscribers:
                if queue.empty():
                    queue.put_nowait(None)
        self._subscribers.clear()


def publish_stats_changed(broadcaster: StatsBroadcaster | None, event_id: UUID) -> None:
    if broadcaster is not None:
        try:
            broadcaster.publish(event_id)
        except Exception:
            # Never include exception text: infrastructure diagnostics can contain
            # participant data. A committed mutation must remain a success.
            logger.warning("Statistics notification failed")


def get_stats_broadcaster(request: Request) -> StatsBroadcaster:
    broadcaster: StatsBroadcaster = request.app.state.stats_broadcaster
    return broadcaster


StatsNotifications = Annotated[StatsBroadcaster, Depends(get_stats_broadcaster)]
