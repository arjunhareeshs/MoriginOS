"""Orders v2: create, read and capture. Every order carries the product SKU as custom_id."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from marginos.core.money import q2
from marginos.integrations.paypal.client import PayPalClient
from marginos.integrations.paypal.schemas import CaptureDetails, parse_capture


def create_order(
    client: PayPalClient,
    *,
    currency: str,
    sku: str,
    title: str,
    quantity: int,
    unit_price: Decimal,
    payment_source: dict[str, Any] | None,
    return_url: str,
    cancel_url: str,
    request_id: str,
) -> dict[str, Any]:
    total = q2(unit_price * quantity)
    body: dict[str, Any] = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "custom_id": sku,
                "amount": {
                    "currency_code": currency,
                    "value": str(total),
                    "breakdown": {"item_total": {"currency_code": currency, "value": str(total)}},
                },
                "items": [
                    {
                        "name": title[:127],
                        "sku": sku,
                        "quantity": str(quantity),
                        "unit_amount": {"currency_code": currency, "value": str(q2(unit_price))},
                    }
                ],
            }
        ],
    }
    if payment_source is not None:
        body["payment_source"] = payment_source
    else:
        body["payment_source"] = {
            "paypal": {
                "experience_context": {
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                    "user_action": "PAY_NOW",
                }
            }
        }
    return client.request("POST", "/v2/checkout/orders", json=body, request_id=request_id)


def get_order(client: PayPalClient, order_id: str) -> dict[str, Any]:
    return client.request("GET", f"/v2/checkout/orders/{order_id}")


def capture_order(client: PayPalClient, order_id: str, request_id: str) -> list[CaptureDetails]:
    response = client.request(
        "POST", f"/v2/checkout/orders/{order_id}/capture", json={}, request_id=request_id
    )
    return captures_from_order(response)


def captures_from_order(order: dict[str, Any]) -> list[CaptureDetails]:
    """Captures embedded in an order response, with order_id and custom_id filled from the unit."""
    out: list[CaptureDetails] = []
    for unit in order.get("purchase_units", []) or []:
        for raw in (unit.get("payments") or {}).get("captures") or []:
            merged = dict(raw)
            merged.setdefault("custom_id", unit.get("custom_id"))
            merged.setdefault("supplementary_data", {"related_ids": {"order_id": order.get("id")}})
            out.append(parse_capture(merged))
    return out
