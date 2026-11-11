"""Webhook ingest (dedupe) and background processing."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from marginos.core.db import SessionScope
from marginos.core.events import bus
from marginos.domains.catalog.models import utcnow
from marginos.domains.webhooks import handlers
from marginos.domains.webhooks.models import WebhookEvent

log = logging.getLogger(__name__)


def ingest(db: Session, event: dict[str, Any], *, verified: bool) -> bool:
    """Store the event. Returns False (and counts the duplicate) if the ID was already seen."""
    resource = event.get("resource") or {}
    stmt = (
        insert(WebhookEvent)
        .values(
            id=event["id"],
            event_type=event.get("event_type", "UNKNOWN"),
            resource_type=event.get("resource_type"),
            resource_id=resource.get("id"),
            verified=verified,
            raw=event,
        )
        .on_conflict_do_nothing(index_elements=[WebhookEvent.id])
        .returning(WebhookEvent.id)
    )
    stored = db.execute(stmt).scalar_one_or_none() is not None
    if not stored:
        db.execute(
            update(WebhookEvent)
            .where(WebhookEvent.id == event["id"])
            .values(duplicate_count=WebhookEvent.duplicate_count + 1)
        )
        log.info("webhook duplicate ignored id=%s", event["id"])
    db.flush()
    return stored


def process_event(event_id: str, scope: SessionScope) -> None:
    """Background: run the handler for a stored event; record success or the error."""
    with scope() as db:
        row = db.get(WebhookEvent, event_id)
        if row is None:
            log.warning("webhook %s vanished before processing", event_id)
            return
        try:
            with db.begin_nested():
                handlers.handle(db, row.raw)
            row.processed_at = utcnow()
            row.error = None
        except Exception as exc:  # recorded and visible on the Audit screen
            log.exception("webhook %s handler failed", event_id)
            row.error = f"{type(exc).__name__}: {exc}"[:2000]
        db.flush()
        event_type, resource_id = row.event_type, row.resource_id
    bus.publish(
        "webhook.received",
        {"event_id": event_id, "event_type": event_type, "resource_id": resource_id},
    )
