"""Per-event-type handlers. Filled in by Task 10; unknown types are ignored."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

Handler = Callable[[Session, dict[str, Any]], None]
HANDLERS: dict[str, Handler] = {}


def handle(db: Session, event: dict[str, Any]) -> None:
    handler = HANDLERS.get(event.get("event_type", ""))
    if handler is None:
        log.info("webhook type %s has no handler; stored only", event.get("event_type"))
        return
    handler(db, event)
