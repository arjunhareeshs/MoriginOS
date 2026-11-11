"""Low-level PayPal REST client: cached client-credentials token and JSON requests."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Any

import httpx

from marginos.core.config import get_settings
from marginos.integrations.paypal.errors import PayPalError

log = logging.getLogger(__name__)

TOKEN_SAFETY_MARGIN_S = 60
DEFAULT_TIMEOUT_S = 30.0


class PayPalClient:
    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        http: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http or httpx.Client(timeout=DEFAULT_TIMEOUT_S)
        self._clock = clock
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._lock = threading.Lock()

    def token(self) -> str:
        with self._lock:
            if self._token and self._clock() < self._token_expires_at:
                return self._token
            response = self._http.post(
                f"{self.base_url}/v1/oauth2/token",
                content=b"grant_type=client_credentials",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                auth=(self._client_id, self._client_secret),
            )
            if response.status_code >= 400:
                raise PayPalError(response.status_code, _json_or_text(response))
            payload = response.json()
            self._token = payload["access_token"]
            self._token_expires_at = (
                self._clock() + float(payload.get("expires_in", 0)) - TOKEN_SAFETY_MARGIN_S
            )
            return self._token

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict | list | None = None,
        params: dict | None = None,
        request_id: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        request_headers = {
            "Authorization": f"Bearer {self.token()}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        if request_id:
            request_headers["PayPal-Request-Id"] = request_id
        if headers:
            request_headers.update(headers)
        response = self._http.request(
            method, f"{self.base_url}{path}", json=json, params=params, headers=request_headers
        )
        if response.status_code >= 400:
            body = _json_or_text(response)
            debug_id = body.get("debug_id") if isinstance(body, dict) else None
            log.warning(
                "PayPal %s %s -> %s debug_id=%s", method, path, response.status_code, debug_id
            )
            raise PayPalError(response.status_code, body, debug_id=debug_id)
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()


def _json_or_text(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


@lru_cache
def get_paypal_client() -> PayPalClient:
    settings = get_settings()
    return PayPalClient(
        base_url=settings.paypal_api_base,
        client_id=settings.paypal_client_id,
        client_secret=settings.paypal_client_secret.get_secret_value(),
    )
