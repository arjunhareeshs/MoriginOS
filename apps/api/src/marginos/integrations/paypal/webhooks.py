"""Webhook signature verification (postback) and webhook registration."""

from __future__ import annotations

import json
from collections.abc import Mapping

from marginos.integrations.paypal.client import PayPalClient

WEBHOOK_EVENT_TYPES: list[str] = [
    "CHECKOUT.ORDER.APPROVED",
    "PAYMENT.CAPTURE.COMPLETED",
    "PAYMENT.CAPTURE.DENIED",
    "PAYMENT.CAPTURE.PENDING",
    "PAYMENT.CAPTURE.REFUNDED",
    "PAYMENT.CAPTURE.REVERSED",
    "INVOICING.INVOICE.PAID",
    "INVOICING.INVOICE.CANCELLED",
    "INVOICING.INVOICE.REFUNDED",
    "CUSTOMER.DISPUTE.CREATED",
    "CUSTOMER.DISPUTE.RESOLVED",
]


def _header(headers: Mapping[str, str], name: str) -> str:
    lowered = {k.lower(): v for k, v in headers.items()}
    return lowered.get(name.lower(), "")


def verify_signature(
    client: PayPalClient, headers: Mapping[str, str], raw_body: bytes, webhook_id: str
) -> bool:
    """Postback verification. The event is spliced in as the exact bytes PayPal sent."""
    fields = {
        "transmission_id": _header(headers, "paypal-transmission-id"),
        "transmission_time": _header(headers, "paypal-transmission-time"),
        "cert_url": _header(headers, "paypal-cert-url"),
        "auth_algo": _header(headers, "paypal-auth-algo"),
        "transmission_sig": _header(headers, "paypal-transmission-sig"),
        "webhook_id": webhook_id,
    }
    prefix = json.dumps(fields)[:-1]  # drop the closing brace
    content = prefix.encode("utf-8") + b', "webhook_event": ' + raw_body + b"}"
    response = client._http.post(  # noqa: SLF001 - raw-body request is deliberate
        f"{client.base_url}/v1/notifications/verify-webhook-signature",
        content=content,
        headers={
            "Authorization": f"Bearer {client.token()}",
            "Content-Type": "application/json",
        },
    )
    if response.status_code >= 400:
        return False
    return response.json().get("verification_status") == "SUCCESS"


def ensure_webhook(client: PayPalClient, url: str, event_types: list[str]) -> str:
    """Create the webhook for url, or patch its event list if it already exists. Returns the ID."""
    existing = client.request("GET", "/v1/notifications/webhooks").get("webhooks", [])
    types = [{"name": name} for name in event_types]
    for hook in existing:
        if hook.get("url") == url:
            client.request(
                "PATCH",
                f"/v1/notifications/webhooks/{hook['id']}",
                json=[{"op": "replace", "path": "/event_types", "value": types}],
            )
            return hook["id"]
    created = client.request(
        "POST", "/v1/notifications/webhooks", json={"url": url, "event_types": types}
    )
    return created["id"]
