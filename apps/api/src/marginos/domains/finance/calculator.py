"""Margin maths per capture.

Rules (see spec section 3.3):
- gross, fee, refunds come from PayPal captures and refunds; costs come from the merchant.
- A missing fee is treated as 0 for the arithmetic and reported with fee_known=False.
- A missing unit cost makes contribution and margin None and sets cost_missing=True; never 0.
- Cost of goods is counted even when the capture was refunded (returned goods are not
  assumed to be resaleable). This is documented in the README.
- margin_pct = contribution / gross, four decimal places, None when gross is 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from marginos.core.money import q2, q4

ZERO = Decimal("0")


@dataclass(frozen=True)
class CaptureLine:
    capture_id: str
    product_id: int | None
    currency: str
    gross: Decimal
    paypal_fee: Decimal | None
    refunded: Decimal
    quantity: int
    unit_cost: Decimal | None
    variable_cost_per_unit: Decimal | None
    captured_at: datetime | None


@dataclass(frozen=True)
class MarginResult:
    gross: Decimal
    paypal_fee: Decimal | None
    fee_known: bool
    refunded: Decimal
    net_proceeds: Decimal
    cogs: Decimal | None
    variable: Decimal | None
    contribution: Decimal | None
    margin_pct: Decimal | None
    cost_missing: bool


def capture_margin(line: CaptureLine) -> MarginResult:
    fee_known = line.paypal_fee is not None
    fee = line.paypal_fee if fee_known else ZERO
    net_proceeds = q2(line.gross - fee - line.refunded)

    if line.unit_cost is None:
        return MarginResult(
            gross=q2(line.gross),
            paypal_fee=q2(fee) if fee_known else None,
            fee_known=fee_known,
            refunded=q2(line.refunded),
            net_proceeds=net_proceeds,
            cogs=None,
            variable=None,
            contribution=None,
            margin_pct=None,
            cost_missing=True,
        )

    cogs = q2(line.unit_cost * line.quantity)
    variable = (
        q2(line.variable_cost_per_unit * line.quantity)
        if line.variable_cost_per_unit is not None
        else None
    )
    contribution = q2(net_proceeds - cogs - (variable or ZERO))
    margin_pct = q4(contribution / line.gross) if line.gross != ZERO else None
    return MarginResult(
        gross=q2(line.gross),
        paypal_fee=q2(fee) if fee_known else None,
        fee_known=fee_known,
        refunded=q2(line.refunded),
        net_proceeds=net_proceeds,
        cogs=cogs,
        variable=variable,
        contribution=contribution,
        margin_pct=margin_pct,
        cost_missing=False,
    )
