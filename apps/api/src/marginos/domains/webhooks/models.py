"""Every PayPal webhook delivery we accepted, keyed by PayPal's event ID (dedupe key)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from marginos.core.db import Base
from marginos.domains.catalog.models import utcnow


class WebhookEvent(Base):
    __tablename__ = "webhook_event"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), default=None)
    resource_id: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    duplicate_count: Mapped[int] = mapped_column(default=0)
    raw: Mapped[dict] = mapped_column(JSONB)
