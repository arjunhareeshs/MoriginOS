from datetime import UTC, datetime
from decimal import Decimal

from marginos.domains.finance.calculator import (
    CaptureLine,
    FeeBasis,
    effective_fee_rate,
    simulate,
)


def line(capture_id, *, gross="29.99", fee="1.54", currency="USD"):
    return CaptureLine(
        capture_id=capture_id,
        product_id=1,
        currency=currency,
        gross=Decimal(gross),
        paypal_fee=Decimal(fee) if fee is not None else None,
        refunded=Decimal("0"),
        quantity=1,
        unit_cost=Decimal("27.50"),
        variable_cost_per_unit=None,
        captured_at=datetime(2026, 11, 11, tzinfo=UTC),
    )


BASIS = FeeBasis(rate=Decimal("0.0514"), sample_size=2, currency="USD")


def test_fee_basis_from_two_captures():
    basis = effective_fee_rate([line("C1"), line("C2")], "USD")
    assert basis.rate == Decimal("0.0514")  # 3.08 / 59.98 = 0.05135
    assert basis.sample_size == 2
    assert basis.currency == "USD"


def test_fee_basis_ignores_unknown_fees_and_other_currencies():
    basis = effective_fee_rate(
        [line("C1"), line("C2", fee=None), line("C3", currency="EUR", fee="9.00")], "USD"
    )
    assert basis.sample_size == 1
    assert basis.rate == Decimal("0.0514")  # 1.54 / 29.99 = 0.05135


def test_fee_basis_zero_captures_is_none():
    basis = effective_fee_rate([], "USD")
    assert basis.rate is None
    assert basis.sample_size == 0


def test_simulate_cost_lever():
    result = simulate(
        currency="USD",
        selling_price=Decimal("29.99"),
        alt_unit_cost=Decimal("18.00"),
        fee_basis=BASIS,
    )
    assert result.gross == Decimal("29.99")
    assert result.est_paypal_fee == Decimal("1.54")
    assert result.est_net == Decimal("28.45")
    assert result.cogs == Decimal("18.00")
    assert result.est_contribution == Decimal("10.45")
    assert result.est_margin_pct == Decimal("0.3484")  # 10.45 / 29.99 = 0.34845
    assert result.estimated is True
    assert result.fee_unknown is False


def test_simulate_price_lever_raises_margin():
    low = simulate(
        currency="USD",
        selling_price=Decimal("29.99"),
        alt_unit_cost=Decimal("27.50"),
        fee_basis=BASIS,
    )
    high = simulate(
        currency="USD",
        selling_price=Decimal("34.99"),
        alt_unit_cost=Decimal("27.50"),
        fee_basis=BASIS,
    )
    assert low.est_contribution == Decimal("0.95")
    assert high.est_contribution == Decimal("5.69")  # 34.99 - 1.80 - 27.50
    assert high.est_margin_pct > low.est_margin_pct


def test_simulate_quantity_and_variable_cost():
    result = simulate(
        currency="USD",
        selling_price=Decimal("10.00"),
        alt_unit_cost=Decimal("4.00"),
        quantity=3,
        fee_basis=BASIS,
        variable_cost_per_unit=Decimal("0.50"),
    )
    assert result.gross == Decimal("30.00")
    assert result.cogs == Decimal("12.00")
    assert result.variable == Decimal("1.50")
    assert result.est_paypal_fee == Decimal("1.54")  # 30.00 * 0.0514 = 1.542
    assert result.est_contribution == Decimal("14.96")


def test_simulate_fee_unknown_reports_before_fees():
    result = simulate(
        currency="USD",
        selling_price=Decimal("29.99"),
        alt_unit_cost=Decimal("18.00"),
        fee_basis=FeeBasis(rate=None, sample_size=0, currency="USD"),
    )
    assert result.fee_unknown is True
    assert result.est_paypal_fee is None
    assert result.est_net == Decimal("29.99")
    assert result.est_contribution == Decimal("11.99")


def test_simulate_rejects_currency_mismatch_with_basis():
    import pytest

    with pytest.raises(ValueError):
        simulate(
            currency="EUR",
            selling_price=Decimal("1"),
            alt_unit_cost=Decimal("1"),
            fee_basis=BASIS,
        )
