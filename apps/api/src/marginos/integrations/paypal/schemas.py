"""Typed views over PayPal responses. Parsing is pure so it can be tested from fixtures."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from marginos.core.money import D


@dataclass(frozen=True)
class CaptureDetails:
    capture_id: str
    status: str
    gross: Decimal
    currency: str
    paypal_fee: Decimal | None
    net: Decimal | None
    custom_id: str | None
    order_id: str | None
    captured_at: datetime | None
    raw: dict[str, Any] = field(repr=False)


@dataclass(frozen=True)
class RefundResult:
    refund_id: str
    status: str
    amount: Decimal
    currency: str
    capture_id: str | None
    raw: dict[str, Any] = field(repr=False)


def _money(node: dict | None) -> Decimal | None:
    if not node or "value" not in node:
        return None
    return D(node["value"])


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _link(raw: dict, rel: str) -> str | None:
    for link in raw.get("links", []) or []:
        if link.get("rel") == rel:
            return link.get("href")
    return None


def parse_capture(raw: dict[str, Any]) -> CaptureDetails:
    amount = raw.get("amount") or {}
    breakdown = raw.get("seller_receivable_breakdown") or {}
    related = (raw.get("supplementary_data") or {}).get("related_ids") or {}
    return CaptureDetails(
        capture_id=raw["id"],
        status=raw.get("status", "UNKNOWN"),
        gross=_money(amount) or Decimal("0"),
        currency=amount.get("currency_code", ""),
        paypal_fee=_money(breakdown.get("paypal_fee")),
        net=_money(breakdown.get("net_amount")),
        custom_id=raw.get("custom_id"),
        order_id=related.get("order_id"),
        captured_at=_time(raw.get("create_time")),
        raw=raw,
    )


def parse_refund(raw: dict[str, Any]) -> RefundResult:
    amount = raw.get("amount") or {}
    up = _link(raw, "up")
    capture_id = up.rstrip("/").rsplit("/", 1)[-1] if up and "/captures/" in up else None
    return RefundResult(
        refund_id=raw["id"],
        status=raw.get("status", "UNKNOWN"),
        amount=_money(amount) or Decimal("0"),
        currency=amount.get("currency_code", ""),
        capture_id=capture_id,
        raw=raw,
    )
