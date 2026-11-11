import json

import httpx
import pytest
import respx
from sqlalchemy import select

from marginos.core.config import Settings, get_settings
from marginos.domains.webhooks.models import WebhookEvent
from marginos.integrations.paypal.client import PayPalClient, get_paypal_client

BASE = "https://api-m.sandbox.paypal.com"
HEADERS = {
    "PAYPAL-TRANSMISSION-ID": "tid-1",
    "PAYPAL-TRANSMISSION-TIME": "2026-11-11T12:00:00Z",
    "PAYPAL-CERT-URL": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-1",
    "PAYPAL-AUTH-ALGO": "SHA256withRSA",
    "PAYPAL-TRANSMISSION-SIG": "sig==",
    "Content-Type": "application/json",
}
RAW = (
    b'{"id":"WH-EVT-1","event_type":"PAYMENT.CAPTURE.DENIED","resource_type":"capture",'
    b'"resource":{"id":"CAP-X","status":"DECLINED"},  "create_time":"2026-11-11T12:00:00Z"}'
)


def _settings(**overrides) -> Settings:
    values = {"paypal_webhook_id": "WEBHOOK-1", "app_env": "development"} | overrides
    return Settings(_env_file=None, **values)


@pytest.fixture
def wired(client):
    app = client.app
    app.dependency_overrides[get_paypal_client] = lambda: PayPalClient(
        base_url=BASE, client_id="cid", client_secret="sec"
    )
    app.dependency_overrides[get_settings] = _settings
    return client


def _mock_verify(respx_mock, status="SUCCESS"):
    respx_mock.post(f"{BASE}/v1/oauth2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
    )
    return respx_mock.post(f"{BASE}/v1/notifications/verify-webhook-signature").mock(
        return_value=httpx.Response(200, json={"verification_status": status})
    )


@respx.mock
def test_invalid_signature_returns_400_and_stores_nothing(wired, db, respx_mock):
    _mock_verify(respx_mock, status="FAILURE")

    response = wired.post("/webhooks/paypal", content=RAW, headers=HEADERS)

    assert response.status_code == 400
    assert db.scalar(select(WebhookEvent).where(WebhookEvent.id == "WH-EVT-1")) is None


@respx.mock
def test_valid_event_stored_once_and_duplicate_ignored(wired, db, respx_mock):
    _mock_verify(respx_mock)

    first = wired.post("/webhooks/paypal", content=RAW, headers=HEADERS)
    second = wired.post("/webhooks/paypal", content=RAW, headers=HEADERS)

    assert first.status_code == 200 and first.json() == {"stored": True}
    assert second.status_code == 200 and second.json() == {"stored": False}
    rows = db.scalars(select(WebhookEvent).where(WebhookEvent.id == "WH-EVT-1")).all()
    assert len(rows) == 1
    assert rows[0].verified is True
    assert rows[0].event_type == "PAYMENT.CAPTURE.DENIED"
    assert rows[0].resource_id == "CAP-X"
    assert rows[0].processed_at is not None


@respx.mock
def test_raw_body_forwarded_unchanged(wired, respx_mock):
    route = _mock_verify(respx_mock)

    wired.post("/webhooks/paypal", content=RAW, headers=HEADERS)

    assert RAW in route.calls[0].request.content
    sent = json.loads(route.calls[0].request.content)
    assert sent["webhook_id"] == "WEBHOOK-1"
    assert sent["transmission_id"] == "tid-1"


@respx.mock
def test_skip_verify_in_development_does_not_call_paypal(wired, db, respx_mock):
    route = _mock_verify(respx_mock)
    wired.app.dependency_overrides[get_settings] = lambda: _settings(
        paypal_webhook_skip_verify=True
    )

    response = wired.post("/webhooks/paypal", content=RAW, headers=HEADERS)

    assert response.status_code == 200
    assert route.call_count == 0
    row = db.scalar(select(WebhookEvent).where(WebhookEvent.id == "WH-EVT-1"))
    assert row.verified is False


def test_malformed_json_returns_400(wired):
    wired.app.dependency_overrides[get_settings] = lambda: _settings(
        paypal_webhook_skip_verify=True
    )
    response = wired.post("/webhooks/paypal", content=b"not json", headers=HEADERS)
    assert response.status_code == 400


@respx.mock
def test_missing_webhook_id_rejects_instead_of_skipping(wired, respx_mock):
    _mock_verify(respx_mock)
    wired.app.dependency_overrides[get_settings] = lambda: _settings(paypal_webhook_id="")

    response = wired.post("/webhooks/paypal", content=RAW, headers=HEADERS)

    assert response.status_code == 503
