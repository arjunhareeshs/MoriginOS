import asyncio
import threading

from marginos.core.events import EventBus, format_sse


async def _next(gen):
    return await asyncio.wait_for(gen.__anext__(), timeout=2)


async def test_subscriber_receives_published_payload():
    bus = EventBus()
    gen = bus.subscribe()
    first = asyncio.ensure_future(_next(gen))
    await asyncio.sleep(0)  # let the subscription register

    bus.publish("ledger.changed", {"capture_id": "C1"})

    event = await first
    assert event == {"topic": "ledger.changed", "payload": {"capture_id": "C1"}}
    await gen.aclose()


async def test_publish_from_thread_is_delivered():
    bus = EventBus()
    gen = bus.subscribe()
    first = asyncio.ensure_future(_next(gen))
    await asyncio.sleep(0)

    thread = threading.Thread(target=bus.publish, args=("task.changed", {"task_id": 7}))
    thread.start()
    thread.join()

    assert (await first)["payload"] == {"task_id": 7}
    await gen.aclose()


async def test_topic_filter_skips_other_topics():
    bus = EventBus()
    gen = bus.subscribe({"task.changed"})
    first = asyncio.ensure_future(_next(gen))
    await asyncio.sleep(0)

    bus.publish("ledger.changed", {"x": 1})
    bus.publish("task.changed", {"x": 2})

    assert (await first)["payload"] == {"x": 2}
    await gen.aclose()


async def test_unsubscribe_on_close_removes_subscriber():
    bus = EventBus()
    gen = bus.subscribe()
    pending = asyncio.ensure_future(_next(gen))
    await asyncio.sleep(0)
    assert bus.subscriber_count == 1
    pending.cancel()
    await asyncio.gather(pending, return_exceptions=True)
    await gen.aclose()
    assert bus.subscriber_count == 0


def test_format_sse():
    text = format_sse("ledger.changed", {"a": "1.50"})
    assert text == 'event: ledger.changed\ndata: {"a": "1.50"}\n\n'


def test_events_endpoint_streams_published_event(client):
    from marginos.core.events import bus

    def publish_soon():
        import time

        for _ in range(50):
            if bus.subscriber_count:
                break
            time.sleep(0.02)
        bus.publish("ledger.changed", {"capture_id": "C9"})

    threading.Thread(target=publish_soon).start()
    with client.stream("GET", "/events?max_events=1") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())

    assert "event: ledger.changed" in body
    assert '"capture_id": "C9"' in body
