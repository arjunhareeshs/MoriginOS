import json

import httpx
import respx

from marginos.integrations.paypal.client import PayPalClient
from marginos.integrations.paypal.webhooks import (
    WEBHOOK_EVENT_TYPES,
    ensure_webhook,
    verify_signature,
)

BASE = "https://api-m.sandbox.paypal.com"


def _client() -> PayPalClient:
    return PayPalClient(base_url=BASE, client_id="cid", client_secret="sec")


def _auth(respx_mock):
    respx_mock.post(f"{BASE}/v1/oauth2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
    )


HEADERS = {
    "paypal-transmission-id": "tid-1",
    "paypal-transmission-time": "2026-11-11T12:00:00Z",
    "paypal-cert-url": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-1",
    "paypal-auth-algo": "SHA256withRSA",
    "paypal-transmission-sig": "sig==",
}


@respx.mock
def test_verify_signature_sends_raw_event_bytes(respx_mock):
    _auth(respx_mock)
    route = respx_mock.post(f"{BASE}/v1/notifications/verify-webhook-signature").mock(
        return_value=httpx.Response(200, json={"verification_status": "SUCCESS"})
    )
    raw = b'{"id":"WH-1","event_type":"PAYMENT.CAPTURE.REFUNDED","resource":{"id":"R1"},"z":  1}'

    ok = verify_signature(_client(), HEADERS, raw, "WEBHOOK-ID-1")

    assert ok is True
    content = route.calls[0].request.content
    assert raw in content
    sent = json.loads(content)
    assert sent["transmission_id"] == "tid-1"
    assert sent["auth_algo"] == "SHA256withRSA"
    assert sent["webhook_id"] == "WEBHOOK-ID-1"
    assert sent["webhook_event"]["id"] == "WH-1"


@respx.mock
def test_verify_signature_failure_returns_false(respx_mock):
    _auth(respx_mock)
    respx_mock.post(f"{BASE}/v1/notifications/verify-webhook-signature").mock(
        return_value=httpx.Response(200, json={"verification_status": "FAILURE"})
    )
    assert verify_signature(_client(), HEADERS, b"{}", "W") is False


@respx.mock
def test_ensure_webhook_patches_existing(respx_mock):
    _auth(respx_mock)
    url = "https://demo.example/webhooks/paypal"
    respx_mock.get(f"{BASE}/v1/notifications/webhooks").mock(
        return_value=httpx.Response(
            200, json={"webhooks": [{"id": "WH-EXIST", "url": url, "event_types": []}]}
        )
    )
    patch = respx_mock.patch(f"{BASE}/v1/notifications/webhooks/WH-EXIST").mock(
        return_value=httpx.Response(200, json={"id": "WH-EXIST"})
    )
    create = respx_mock.post(f"{BASE}/v1/notifications/webhooks")

    webhook_id = ensure_webhook(_client(), url, WEBHOOK_EVENT_TYPES)

    assert webhook_id == "WH-EXIST"
    assert patch.call_count == 1
    assert create.call_count == 0
    sent = json.loads(patch.calls[0].request.content)
    assert sent[0]["path"] == "/event_types"
    assert {"name": "PAYMENT.CAPTURE.REFUNDED"} in sent[0]["value"]


@respx.mock
def test_ensure_webhook_creates_when_missing(respx_mock):
    _auth(respx_mock)
    respx_mock.get(f"{BASE}/v1/notifications/webhooks").mock(
        return_value=httpx.Response(200, json={"webhooks": []})
    )
    create = respx_mock.post(f"{BASE}/v1/notifications/webhooks").mock(
        return_value=httpx.Response(201, json={"id": "WH-NEW"})
    )

    assert ensure_webhook(_client(), "https://demo.example/webhooks/paypal", ["A.B"]) == "WH-NEW"
    sent = json.loads(create.calls[0].request.content)
    assert sent["url"] == "https://demo.example/webhooks/paypal"
    assert sent["event_types"] == [{"name": "A.B"}]


def test_event_type_list_covers_spec():
    for name in [
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
    ]:
        assert name in WEBHOOK_EVENT_TYPES
