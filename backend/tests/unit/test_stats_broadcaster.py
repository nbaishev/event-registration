import asyncio
from uuid import uuid4

import pytest

from app.events.broadcaster import StatsBroadcaster, publish_stats_changed


def test_threadsafe_publish_isolated_bounded_and_unsubscribe():
    async def scenario():
        broadcaster = StatsBroadcaster()
        broadcaster.startup()
        first, other = uuid4(), uuid4()
        queue = broadcaster.subscribe(first)
        second = broadcaster.subscribe(first)
        unrelated = broadcaster.subscribe(other)
        await asyncio.to_thread(
            lambda: [broadcaster.publish(first) for _ in range(100)]
        )
        assert queue.qsize() == second.qsize() == 1
        assert unrelated.empty()
        assert await queue.get() is None
        broadcaster.unsubscribe(first, second)
        second.get_nowait()
        await asyncio.to_thread(broadcaster.publish, first)
        assert queue.qsize() == 1
        assert second.empty()
        broadcaster.unsubscribe(first, queue)
        broadcaster.unsubscribe(first, queue)
        broadcaster.shutdown()

    asyncio.run(scenario())


def test_shutdown_wakes_consumers_and_discards_scheduled_signals():
    async def scenario():
        broadcaster = StatsBroadcaster()
        broadcaster.startup()
        event = uuid4()
        queue = broadcaster.subscribe(event)
        broadcaster.publish(event)
        broadcaster.shutdown()
        assert await queue.get() is None
        assert broadcaster.closed
        with pytest.raises(RuntimeError):
            broadcaster.subscribe(event)
        broadcaster.publish(event)
        await asyncio.to_thread(lambda: None)
        assert queue.empty()

    asyncio.run(scenario())


def test_postcommit_publish_failure_is_best_effort(caplog):
    class FailedBroadcaster:
        def publish(self, event_id):
            raise RuntimeError("private diagnostic")

    publish_stats_changed(FailedBroadcaster(), uuid4())
    assert "Statistics notification failed" in caplog.text
    assert "private diagnostic" not in caplog.text


def test_frames_heartbeat_signal_and_shutdown(monkeypatch):
    from app.events import stream

    async def scenario():
        broadcaster = StatsBroadcaster()
        broadcaster.startup()
        queue = broadcaster.subscribe(uuid4())
        frames = stream.stats_frames(broadcaster, queue)
        actual_wait = asyncio.wait_for

        async def timeout(awaitable, *, timeout):
            assert timeout == 15
            awaitable.close()
            raise TimeoutError

        monkeypatch.setattr(stream.asyncio, "wait_for", timeout)
        assert await anext(frames) == ": heartbeat\n\n"
        monkeypatch.setattr(stream.asyncio, "wait_for", actual_wait)
        queue.put_nowait(None)
        assert await anext(frames) == "event: stats_changed\ndata: {}\n\n"
        waiting = asyncio.create_task(anext(frames))
        # Let the consumer start waiting, then use the lifecycle shutdown wakeup.
        await asyncio.sleep(0)
        broadcaster.shutdown()
        with pytest.raises(StopAsyncIteration):
            await waiting

    asyncio.run(scenario())


def test_response_cancellation_before_body_cleans_subscription():
    from app.events.stream import StatsStreamResponse

    async def scenario():
        broadcaster = StatsBroadcaster()
        broadcaster.startup()
        event_id = uuid4()
        response = StatsStreamResponse(broadcaster, event_id)

        async def receive():
            await asyncio.Future()

        async def send(message):
            raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await response(
                {"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send
            )
        assert event_id not in broadcaster._subscribers
        broadcaster.shutdown()

    asyncio.run(scenario())
