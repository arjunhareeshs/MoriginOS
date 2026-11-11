"""Pydantic schemas for operations payloads."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class RefundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    paypal_refund_id: str
    amount: Decimal
    currency: str
    status: str
    reason: str | None
    source: str
    created_at: datetime


class CaptureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    paypal_capture_id: str
    product_id: int | None
    quantity: int
    gross: Decimal
    paypal_fee: Decimal | None
    fee_known: bool
    net: Decimal | None
    currency: str
    status: str
    leakage: bool
    captured_at: datetime | None
    source: str
    refunds: list[RefundOut] = []
