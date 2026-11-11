from decimal import Decimal

import pytest

from marginos.domains.catalog import service


def _product(db, sku="EARBUDS-PRO", currency="USD"):
    return service.upsert_product(
        db, sku=sku, title="Wireless Earbuds Pro", selling_price=Decimal("29.99"), currency=currency
    )


def test_set_cost_creates_new_row_and_current_cost_returns_latest(db):
    product = _product(db)
    service.set_cost(db, product.id, unit_cost=Decimal("20.00"), variable_cost_per_unit=None)
    service.set_cost(
        db, product.id, unit_cost=Decimal("27.50"), variable_cost_per_unit=Decimal("0.50")
    )

    current = service.current_cost(db, product.id)

    assert current is not None
    assert current.unit_cost == Decimal("27.50")
    assert current.variable_cost_per_unit == Decimal("0.50")
    assert current.label == "Sample data"
    assert current.currency == "USD"


def test_upsert_product_is_idempotent_on_sku(db):
    first = _product(db)
    second = service.upsert_product(
        db,
        sku="EARBUDS-PRO",
        title="Earbuds Pro v2",
        selling_price=Decimal("31.00"),
        currency="USD",
    )

    assert second.id == first.id
    assert service.get_product_by_sku(db, "EARBUDS-PRO").title == "Earbuds Pro v2"
    assert service.get_product_by_sku(db, "EARBUDS-PRO").selling_price == Decimal("31.00")


def test_cost_currency_must_match_product(db):
    product = _product(db, currency="EUR")
    with pytest.raises(ValueError):
        service.set_cost(
            db, product.id, unit_cost=Decimal("1.00"), variable_cost_per_unit=None, currency="USD"
        )


def test_update_price_rejects_negative(db):
    product = _product(db)
    with pytest.raises(ValueError):
        service.update_price(db, product.id, Decimal("-1.00"))


def test_ensure_merchant_is_idempotent(db):
    first = service.ensure_merchant(db)
    second = service.ensure_merchant(db)
    assert first.id == second.id
