from datetime import UTC, datetime
from decimal import Decimal

from marginos.domains.finance.calculator import CaptureLine, capture_margin


def line(
    *,
    gross="29.99",
    fee="1.54",
    refunded="0",
    qty=1,
    cost="27.50",
    variable=None,
    currency="USD",
):
    return CaptureLine(
        capture_id="CAP-1",
        product_id=1,
        currency=currency,
        gross=Decimal(gross),
        paypal_fee=Decimal(fee) if fee is not None else None,
        refunded=Decimal(refunded),
        quantity=qty,
        unit_cost=Decimal(cost) if cost is not None else None,
        variable_cost_per_unit=Decimal(variable) if variable is not None else None,
        captured_at=datetime(2026, 11, 11, tzinfo=UTC),
    )


def test_basic_margin():
    result = capture_margin(line())

    assert result.net_proceeds == Decimal("28.45")
    assert result.cogs == Decimal("27.50")
    assert result.contribution == Decimal("0.95")
    assert result.margin_pct == Decimal("0.0317")
    assert result.fee_known is True
    assert result.cost_missing is False


def test_full_refund_counts_cogs():
    result = capture_margin(line(refunded="29.99"))

    assert result.net_proceeds == Decimal("-1.54")
    assert result.contribution == Decimal("-29.04")


def test_partial_refund():
    result = capture_margin(line(refunded="10.00"))
    assert result.net_proceeds == Decimal("18.45")


def test_missing_fee_sets_fee_known_false():
    result = capture_margin(line(fee=None))

    assert result.fee_known is False
    assert result.paypal_fee is None
    assert result.net_proceeds == Decimal("29.99")


def test_missing_cost_sets_cost_missing_and_none_contribution():
    result = capture_margin(line(cost=None))

    assert result.cost_missing is True
    assert result.cogs is None
    assert result.contribution is None
    assert result.margin_pct is None
    assert result.net_proceeds == Decimal("28.45")


def test_zero_gross_gives_none_margin_pct():
    result = capture_margin(line(gross="0", fee="0"))
    assert result.margin_pct is None
    assert result.contribution == Decimal("-27.50")


def test_quantity_multiplies_cogs_and_variable():
    result = capture_margin(line(gross="60.00", fee="2.58", qty=3, cost="2.00", variable="0.50"))

    assert result.cogs == Decimal("6.00")
    assert result.variable == Decimal("1.50")
    assert result.contribution == Decimal("49.92")
