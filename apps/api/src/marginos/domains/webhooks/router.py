"""POST /webhooks/paypal: raw body -> postback verification -> dedupe -> 200 -> background."""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from marginos.core.config import Settings, get_settings
from marginos.core.db import SessionScope, get_db, get_session_scope
from marginos.domains.webhooks.service import ingest, process_event
from marginos.integrations.paypal.client import PayPalClient, get_paypal_client
from marginos.integrations.paypal.errors import PayPalError
from marginos.integrations.paypal.webhooks import verify_signature

log = logging.getLogger(__name__)
router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/paypal")
async def paypal_webhook(
    request: Request,
    background: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    paypal: Annotated[PayPalClient, Depends(get_paypal_client)],
    scope: Annotated[SessionScope, Depends(get_session_scope)],
) -> dict[str, bool]:
    raw = await request.body()
    skip = settings.paypal_webhook_skip_verify and settings.app_env == "development"
    if skip:
        log.warning("WEBHOOK SIGNATURE VERIFICATION SKIPPED (development flag)")
        verified = False
    else:
        if not settings.paypal_webhook_id:
            raise HTTPException(503, "webhook id not configured")
        try:
            verified = verify_signature(paypal, request.headers, raw, settings.paypal_webhook_id)
        except PayPalError as exc:
            log.error("webhook verification call failed: %s", exc)
            raise HTTPException(503, "verification unavailable") from exc
        if not verified:
            log.warning("webhook rejected: signature verification failed")
            raise HTTPException(400, "signature verification failed")
    try:
        event = json.loads(raw)
        event_id = event["id"]
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, "malformed event") from exc

    stored = ingest(db, event, verified=verified)
    db.commit()
    log.info(
        "webhook %s id=%s type=%s verified=%s",
        "stored" if stored else "duplicate",
        event_id,
        event.get("event_type"),
        verified,
    )
    if stored:
        background.add_task(process_event, event_id, scope)
    return {"stored": stored}
