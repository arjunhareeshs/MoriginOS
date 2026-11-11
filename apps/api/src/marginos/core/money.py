"""Decimal money helpers. Every amount in MarginOS is a Decimal plus an ISO 4217 code."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


def D(value: str | int | float | Decimal) -> Decimal:  # noqa: N802 - short constructor
    """Build a Decimal without binary-float artefacts (floats go through repr)."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(repr(value))
    return Decimal(str(value))


def q2(value: Decimal) -> Decimal:
    """Quantise to two decimal places, rounding half up."""
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def q4(value: Decimal) -> Decimal:
    """Quantise to four decimal places (ratios such as margin percentage)."""
    return value.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


def validate_currency(code: str) -> str:
    if not CURRENCY_RE.match(code or ""):
        raise ValueError(f"invalid currency code: {code!r}")
    return code
