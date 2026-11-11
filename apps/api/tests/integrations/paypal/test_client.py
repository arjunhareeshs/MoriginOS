import httpx
import pytest
import respx

from marginos.integrations.paypal.client import PayPalClient
from marginos.integrations.paypal.errors import PayPalError

BASE = "https://api-m.sandbox.paypal.com"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _client(clock: FakeClock | None = None) -> PayPalClient:
    return PayPalClient(
        base_url=BASE, client_id="cid", client_secret="csecret", clock=clock or FakeClock()
    )


def _token_route(respx_mock, expires_in: int = 3600):
    return respx_mock.post(f"{BASE}/v1/oauth2/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "tok-1", "token_type": "Bearer", "expires_in": expires_in}
        )
    )


@respx.mock
def test_token_cached_until_expiry(respx_mock):
    token_route = _token_route(respx_mock)
    respx_mock.get(f"{BASE}/v2/checkout/orders/1").mock(return_value=httpx.Response(200, json={}))
    client = _client()

    client.request("GET", "/v2/checkout/orders/1")
    client.request("GET", "/v2/checkout/orders/1")

    assert token_route.call_count == 1


@respx.mock
def test_token_refreshed_after_expiry(respx_mock):
    token_route = _token_route(respx_mock, expires_in=120)
    respx_mock.get(f"{BASE}/v2/checkout/orders/1").mock(return_value=httpx.Response(200, json={}))
    clock = FakeClock()
    client = _client(clock)

    client.request("GET", "/v2/checkout/orders/1")
    clock.now += 120 - 60 + 1  # past the expires_in - 60 safety margin
    client.request("GET", "/v2/checkout/orders/1")

    assert token_route.call_count == 2


@respx.mock
def test_token_request_uses_basic_auth_and_client_credentials(respx_mock):
    token_route = _token_route(respx_mock)
    client = _client()

    client.token()

    sent = token_route.calls[0].request
    assert sent.headers["Authorization"].startswith("Basic ")
    assert sent.content == b"grant_type=client_credentials"


@respx.mock
def test_request_sets_request_id_and_bearer_headers(respx_mock):
    _token_route(respx_mock)
    route = respx_mock.post(f"{BASE}/v2/payments/captures/CAP1/refund").mock(
        return_value=httpx.Response(201, json={"id": "R1"})
    )
    client = _client()

    body = client.request("POST", "/v2/payments/captures/CAP1/refund", json={}, request_id="req-1")

    sent = route.calls[0].request
    assert sent.headers["PayPal-Request-Id"] == "req-1"
    assert sent.headers["Authorization"] == "Bearer tok-1"
    assert body == {"id": "R1"}


@respx.mock
def test_error_raises_paypal_error_with_debug_id(respx_mock):
    _token_route(respx_mock)
    respx_mock.post(f"{BASE}/v2/payments/captures/CAP1/refund").mock(
        return_value=httpx.Response(
            422,
            json={"name": "UNPROCESSABLE_ENTITY", "debug_id": "dbg-9", "details": []},
        )
    )
    client = _client()

    with pytest.raises(PayPalError) as excinfo:
        client.request("POST", "/v2/payments/captures/CAP1/refund", json={}, request_id="r")

    assert excinfo.value.status_code == 422
    assert excinfo.value.debug_id == "dbg-9"
    assert excinfo.value.body["name"] == "UNPROCESSABLE_ENTITY"


@respx.mock
def test_token_failure_raises_paypal_error_without_leaking_secret(respx_mock):
    respx_mock.post(f"{BASE}/v1/oauth2/token").mock(
        return_value=httpx.Response(401, json={"error": "invalid_client"})
    )
    client = _client()

    with pytest.raises(PayPalError) as excinfo:
        client.token()

    assert excinfo.value.status_code == 401
    assert "csecret" not in str(excinfo.value)
