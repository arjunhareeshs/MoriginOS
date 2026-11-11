from datetime import UTC, datetime
from decimal import Decimal

from marginos.domains.finance.calculator import (
    CaptureLine,
    currency_totals,
    explain_product,
    product_summaries,
    rank_products,
)


def line(
    capture_id,
    product_id,
    *,
    gross="29.99",
    fee="1.54",
    refunded="0",
    cost="27.50",
    currency="USD",
    qty=1,
):
    return CaptureLine(
        capture_id=capture_id,
        product_id=product_id,
        currency=currency,
        gross=Decimal(gross),
        paypal_fee=Decimal(fee) if fee is not None else None,
        refunded=Decimal(refunded),
        quantity=qty,
        unit_cost=Decimal(cost) if cost is not None else None,
        variable_cost_per_unit=None,
        captured_at=datetime(2026, 11, 11, tzinfo=UTC),
    )


# Product 1 (earbuds): 4 good sales + 1 fully refunded -> loss maker.
# Product 2 (case): healthy. Product 3 (eu-item): EUR. Product 4: cost missing.
LINES = [
    line("C1", 1),
    line("C2", 1),
    line("C3", 1),
    line("C4", 1),
    line("C5", 1, refunded="29.99"),
    line("C6", 2, gross="19.99", fee="1.19", cost="6.00"),
    line("C7", 2, gross="19.99", fee="1.19", cost="6.00"),
    line("C8", 3, gross="49.00", fee="2.20", cost="20.00", currency="EUR"),
    line("C9", 4, gross="10.00", fee="0.84", cost=None),
]


def test_product_summary_aggregates_per_product_and_currency():
    summaries = {(s.product_id, s.currency): s for s in product_summaries(LINES)}

    earbuds = summaries[(1, "USD")]
    assert earbuds.capture_count == 5
    assert earbuds.gross == Decimal("149.95")
    assert earbuds.paypal_fee == Decimal("7.70")
    assert earbuds.refunded == Decimal("29.99")
    assert earbuds.net_proceeds == Decimal("112.26")
    assert earbuds.cogs == Decimal("137.50")
    assert earbuds.contribution == Decimal("-25.24")
    assert earbuds.margin_pct == Decimal("-0.1683")
    assert earbuds.capture_ids == ["C1", "C2", "C3", "C4", "C5"]
    assert summaries[(4, "USD")].cost_missing is True
    assert summaries[(4, "USD")].contribution is None


def test_mixed_currencies_produce_two_totals_never_summed():
    totals = {t.currency: t for t in currency_totals(LINES)}

    assert set(totals) == {"USD", "EUR"}
    assert totals["EUR"].gross == Decimal("49.00")
    assert totals["EUR"].capture_count == 1
    assert totals["USD"].gross == Decimal("149.95") + Decimal("39.98") + Decimal("10.00")
    # USD contribution excludes the cost-missing product and says so
    assert totals["USD"].contribution == Decimal("-25.24") + Decimal("25.60")
    assert totals["USD"].cost_missing_count == 1


def test_rank_ascending_puts_loss_maker_first():
    ranked = rank_products(LINES, currency="USD", limit=5)
    assert [s.product_id for s in ranked][:2] == [1, 2]


def test_rank_descending_puts_best_first():
    ranked = rank_products(LINES, currency="USD", limit=5, ascending=False)
    assert ranked[0].product_id == 2


def test_cost_missing_products_sorted_last():
    ranked = rank_products(LINES, currency="USD", limit=5)
    assert ranked[-1].product_id == 4


def test_rank_respects_limit_and_currency():
    assert len(rank_products(LINES, currency="USD", limit=1)) == 1
    assert [s.product_id for s in rank_products(LINES, currency="EUR", limit=5)] == [3]


def test_explain_shares_and_worst_captures():
    explanation = explain_product(LINES, product_id=1, currency="USD")

    assert explanation.summary.contribution == Decimal("-25.24")
    assert explanation.fee_share_pct == Decimal("0.0514")  # 7.70 / 149.95 = 0.05135
    assert explanation.refund_share_pct == Decimal("0.2000")  # 29.99 / 149.95
    assert explanation.cogs_share_pct == Decimal("0.9170")  # 137.50 / 149.95
    assert explanation.worst_captures[0] == ("C5", Decimal("-29.04"))


def test_explain_unknown_product_returns_none():
    assert explain_product(LINES, product_id=99, currency="USD") is None
