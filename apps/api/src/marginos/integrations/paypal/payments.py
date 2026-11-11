"""Payments v2: capture details, refunds."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from marginos.core.money import q2
from marginos.integrations.paypal.client import PayPalClient
from marginos.integrations.paypal.schemas import (
    CaptureDetails,
    RefundResult,
    parse_capture,
    parse_refund,
)


def get_capture(client: PayPalClient, capture_id: str) -> CaptureDetails:
    return parse_capture(client.request("GET", f"/v2/payments/captures/{capture_id}"))


def refund_capture(
    client: PayPalClient,
    capture_id: str,
    *,
    amount: Decimal | None,
    currency: str,
    note: str,
    request_id: str,
) -> RefundResult:
    """Refund a capture. amount=None refunds the full remaining amount."""
    body: dict[str, Any] = {"note_to_payer": note[:255]}
    if amount is not None:
        body["amount"] = {"currency_code": currency, "value": str(q2(amount))}
    response = client.request(
        "POST", f"/v2/payments/captures/{capture_id}/refund", json=body, request_id=request_id
    )
    result = parse_refund(response)
    if result.capture_id is None:
        result = RefundResult(
            refund_id=result.refund_id,
            status=result.status,
            amount=result.amount,
            currency=result.currency or currency,
            capture_id=capture_id,
            raw=result.raw,
        )
    return result


def get_refund(client: PayPalClient, refund_id: str) -> RefundResult:
    return parse_refund(client.request("GET", f"/v2/payments/refunds/{refund_id}"))
