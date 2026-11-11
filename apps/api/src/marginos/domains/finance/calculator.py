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


# --- Aggregation -------------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductSummary:
    product_id: int | None
    currency: str
    capture_count: int
    gross: Decimal
    paypal_fee: Decimal
    refunded: Decimal
    net_proceeds: Decimal
    cogs: Decimal | None
    contribution: Decimal | None
    margin_pct: Decimal | None
    cost_missing: bool
    fee_known_all: bool
    capture_ids: list[str]


@dataclass(frozen=True)
class CurrencyTotal:
    currency: str
    capture_count: int
    gross: Decimal
    paypal_fee: Decimal
    refunded: Decimal
    net_proceeds: Decimal
    contribution: Decimal | None
    margin_pct: Decimal | None
    cost_missing_count: int


@dataclass(frozen=True)
class ProductExplanation:
    summary: ProductSummary
    fee_share_pct: Decimal | None
    refund_share_pct: Decimal | None
    cogs_share_pct: Decimal | None
    worst_captures: list[tuple[str, Decimal]]


def _ratio(part: Decimal | None, whole: Decimal) -> Decimal | None:
    if part is None or whole == ZERO:
        return None
    return q4(part / whole)


def _summarise(key: tuple[int | None, str], lines: list[CaptureLine]) -> ProductSummary:
    results = [capture_margin(line) for line in lines]
    gross = sum((r.gross for r in results), ZERO)
    cost_missing = any(r.cost_missing for r in results)
    cogs = None if cost_missing else sum((r.cogs or ZERO for r in results), ZERO)
    contribution = None if cost_missing else sum((r.contribution or ZERO for r in results), ZERO)
    return ProductSummary(
        product_id=key[0],
        currency=key[1],
        capture_count=len(lines),
        gross=q2(gross),
        paypal_fee=q2(sum((r.paypal_fee or ZERO for r in results), ZERO)),
        refunded=q2(sum((r.refunded for r in results), ZERO)),
        net_proceeds=q2(sum((r.net_proceeds for r in results), ZERO)),
        cogs=q2(cogs) if cogs is not None else None,
        contribution=q2(contribution) if contribution is not None else None,
        margin_pct=_ratio(contribution, gross),
        cost_missing=cost_missing,
        fee_known_all=all(r.fee_known for r in results),
        capture_ids=[line.capture_id for line in lines],
    )


def product_summaries(lines: list[CaptureLine]) -> list[ProductSummary]:
    """One summary per (product, currency). Currencies are never combined."""
    groups: dict[tuple[int | None, str], list[CaptureLine]] = {}
    for line in lines:
        groups.setdefault((line.product_id, line.currency), []).append(line)
    return [_summarise(key, group) for key, group in groups.items()]


def rank_products(
    lines: list[CaptureLine], *, currency: str, limit: int, ascending: bool = True
) -> list[ProductSummary]:
    """Rank by margin % within one currency. Products with missing cost always sort last."""
    summaries = [s for s in product_summaries(lines) if s.currency == currency]
    known = [s for s in summaries if s.margin_pct is not None]
    unknown = [s for s in summaries if s.margin_pct is None]
    known.sort(key=lambda s: s.margin_pct, reverse=not ascending)
    return (known + unknown)[:limit]


def currency_totals(lines: list[CaptureLine]) -> list[CurrencyTotal]:
    """Totals per currency. Contribution covers only products with known cost."""
    by_currency: dict[str, list[ProductSummary]] = {}
    for summary in product_summaries(lines):
        by_currency.setdefault(summary.currency, []).append(summary)
    totals: list[CurrencyTotal] = []
    for currency, summaries in sorted(by_currency.items()):
        known = [s for s in summaries if s.contribution is not None]
        gross = sum((s.gross for s in summaries), ZERO)
        known_gross = sum((s.gross for s in known), ZERO)
        contribution = sum((s.contribution for s in known), ZERO) if known else None
        totals.append(
            CurrencyTotal(
                currency=currency,
                capture_count=sum(s.capture_count for s in summaries),
                gross=q2(gross),
                paypal_fee=q2(sum((s.paypal_fee for s in summaries), ZERO)),
                refunded=q2(sum((s.refunded for s in summaries), ZERO)),
                net_proceeds=q2(sum((s.net_proceeds for s in summaries), ZERO)),
                contribution=q2(contribution) if contribution is not None else None,
                margin_pct=_ratio(contribution, known_gross),
                cost_missing_count=sum(1 for s in summaries if s.cost_missing),
            )
        )
    return totals


def explain_product(
    lines: list[CaptureLine], product_id: int, currency: str
) -> ProductExplanation | None:
    own = [ln for ln in lines if ln.product_id == product_id and ln.currency == currency]
    if not own:
        return None
    summary = _summarise((product_id, currency), own)
    per_capture = [
        (ln.capture_id, capture_margin(ln).contribution)
        for ln in own
        if capture_margin(ln).contribution is not None
    ]
    per_capture.sort(key=lambda item: item[1])
    return ProductExplanation(
        summary=summary,
        fee_share_pct=_ratio(summary.paypal_fee, summary.gross),
        refund_share_pct=_ratio(summary.refunded, summary.gross),
        cogs_share_pct=_ratio(summary.cogs, summary.gross),
        worst_captures=per_capture[:3],
    )
