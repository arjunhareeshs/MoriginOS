import json
from decimal import Decimal
from pathlib import Path

import httpx
import respx

from marginos.integrations.paypal.client import PayPalClient
from marginos.integrations.paypal.orders import capture_order, create_order
from marginos.integrations.paypal.payments import get_capture, refund_capture

BASE = "https://api-m.sandbox.paypal.com"
FIXTURES = Path(__file__).parent / "fixtures"


def _client() -> PayPalClient:
    return PayPalClient(base_url=BASE, client_id="cid", client_secret="sec")


def _auth(respx_mock):
    respx_mock.post(f"{BASE}/v1/oauth2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
    )


@respx.mock
def test_refund_capture_full_omits_amount(respx_mock):
    _auth(respx_mock)
    route = respx_mock.post(f"{BASE}/v2/payments/captures/CAP-1/refund").mock(
        return_value=httpx.Response(
            201, json=json.loads((FIXTURES / "refund_completed.json").read_text())
        )
    )

    result = refund_capture(
        _client(), "CAP-1", amount=None, currency="USD", note="full", request_id="apr-1"
    )

    sent = json.loads(route.calls[0].request.content)
    assert "amount" not in sent
    assert sent["note_to_payer"] == "full"
    assert route.calls[0].request.headers["PayPal-Request-Id"] == "apr-1"
    assert result.refund_id == "REF-TEST-001"


@respx.mock
def test_refund_capture_partial_sends_amount(respx_mock):
    _auth(respx_mock)
    route = respx_mock.post(f"{BASE}/v2/payments/captures/CAP-1/refund").mock(
        return_value=httpx.Response(
            201, json=json.loads((FIXTURES / "refund_completed.json").read_text())
        )
    )

    refund_capture(
        _client(), "CAP-1", amount=Decimal("5.00"), currency="USD", note="p", request_id="apr-2"
    )

    sent = json.loads(route.calls[0].request.content)
    assert sent["amount"] == {"currency_code": "USD", "value": "5.00"}


@respx.mock
def test_get_capture_parses_details(respx_mock):
    _auth(respx_mock)
    respx_mock.get(f"{BASE}/v2/payments/captures/CAP-TEST-001").mock(
        return_value=httpx.Response(
            200, json=json.loads((FIXTURES / "capture_completed.json").read_text())
        )
    )

    details = get_capture(_client(), "CAP-TEST-001")

    assert details.paypal_fee == Decimal("1.54")


@respx.mock
def test_create_order_sets_custom_id_and_item_breakdown(respx_mock):
    _auth(respx_mock)
    route = respx_mock.post(f"{BASE}/v2/checkout/orders").mock(
        return_value=httpx.Response(201, json={"id": "ORD-9", "status": "CREATED"})
    )

    order = create_order(
        _client(),
        currency="USD",
        sku="EARBUDS-PRO",
        title="Wireless Earbuds Pro",
        quantity=2,
        unit_price=Decimal("29.99"),
        payment_source=None,
        return_url="https://x/return",
        cancel_url="https://x/cancel",
        request_id="seed-1",
    )

    sent = json.loads(route.calls[0].request.content)
    unit = sent["purchase_units"][0]
    assert sent["intent"] == "CAPTURE"
    assert unit["custom_id"] == "EARBUDS-PRO"
    assert unit["amount"] == {
        "currency_code": "USD",
        "value": "59.98",
        "breakdown": {"item_total": {"currency_code": "USD", "value": "59.98"}},
    }
    assert unit["items"][0]["sku"] == "EARBUDS-PRO"
    assert unit["items"][0]["quantity"] == "2"
    assert order["id"] == "ORD-9"


@respx.mock
def test_capture_order_returns_capture_details(respx_mock):
    _auth(respx_mock)
    capture = json.loads((FIXTURES / "capture_completed.json").read_text())
    respx_mock.post(f"{BASE}/v2/checkout/orders/ORD-1/capture").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": "ORD-1",
                "status": "COMPLETED",
                "purchase_units": [
                    {"custom_id": "EARBUDS-PRO", "payments": {"captures": [capture]}}
                ],
            },
        )
    )

    captures = capture_order(_client(), "ORD-1", request_id="cap-1")

    assert [c.capture_id for c in captures] == ["CAP-TEST-001"]
    assert captures[0].order_id == "ORD-TEST-001"
