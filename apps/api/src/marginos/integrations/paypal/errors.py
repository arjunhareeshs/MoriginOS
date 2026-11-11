"""PayPal API error. Carries status, body and PayPal's debug_id; never carries credentials."""

from __future__ import annotations

from typing import Any


class PayPalError(Exception):
    def __init__(self, status_code: int, body: Any, *, debug_id: str | None = None) -> None:
        self.status_code = status_code
        self.body = body
        self.debug_id = debug_id
        name = body.get("name") if isinstance(body, dict) else None
        super().__init__(f"PayPal {status_code} {name or ''} debug_id={debug_id or '-'}".strip())
