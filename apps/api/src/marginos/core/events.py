"""In-process pub/sub feeding the Server-Sent Events stream.

Topics: ledger.changed, task.changed, approval.changed, webhook.received.
publish() is safe to call from any thread (webhook background tasks run in a threadpool).
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

TOPICS = frozenset({"ledger.changed", "task.changed", "approval.changed", "webhook.received"})
KEEPALIVE_S = 15.0


@dataclass(eq=False)
class _Subscriber:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue
    topics: frozenset[str] | None


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[_Subscriber] = []
        self._lock = threading.Lock()

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        event = {"topic": topic, "payload": payload}
        with self._lock:
            targets = [s for s in self._subscribers if s.topics is None or topic in s.topics]
        for sub in targets:
            try:
                sub.loop.call_soon_threadsafe(sub.queue.put_nowait, event)
            except RuntimeError:  # loop already closed; subscriber is gone
                self._remove(sub)

    async def subscribe(self, topics: set[str] | None = None) -> AsyncIterator[dict[str, Any]]:
        sub = _Subscriber(
            loop=asyncio.get_running_loop(),
            queue=asyncio.Queue(),
            topics=frozenset(topics) if topics else None,
        )
        with self._lock:
            self._subscribers.append(sub)
        try:
            while True:
                yield await sub.queue.get()
        finally:
            self._remove(sub)

    def _remove(self, sub: _Subscriber) -> None:
        with self._lock:
            if sub in self._subscribers:
                self._subscribers.remove(sub)


bus = EventBus()


def format_sse(topic: str, payload: dict[str, Any]) -> str:
    return f"event: {topic}\ndata: {json.dumps(payload, default=str)}\n\n"


router = APIRouter(tags=["events"])


@router.get("/events")
async def events(
    request: Request,
    task_id: int | None = None,
    max_events: int | None = Query(default=None, ge=1, le=100),
) -> StreamingResponse:
    """SSE stream of change notifications. max_events turns it into a long-poll."""

    async def stream() -> AsyncIterator[str]:
        sent = 0
        gen = bus.subscribe()
        pending: asyncio.Future | None = None
        try:
            yield ": connected\n\n"
            while max_events is None or sent < max_events:
                if await request.is_disconnected():
                    break
                pending = pending or asyncio.ensure_future(gen.__anext__())
                done, _ = await asyncio.wait({pending}, timeout=KEEPALIVE_S)
                if not done:
                    yield ": keepalive\n\n"
                    continue
                event, pending = pending.result(), None
                payload = event["payload"]
                if task_id is not None and payload.get("task_id") != task_id:
                    continue
                yield format_sse(event["topic"], payload)
                sent += 1
        finally:
            if pending is not None:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
            await gen.aclose()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
