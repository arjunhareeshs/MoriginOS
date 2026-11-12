import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))

from seed_data import CATALOG  # noqa: E402
from seed_sandbox import select_products  # noqa: E402


def test_seed_catalog_has_one_designed_loss_maker():
    losers = [p for p in CATALOG if p.unit_cost > p.selling_price * Decimal("0.9")]
    assert [p.sku for p in losers] == ["EARBUDS-PRO"]


def test_seed_catalog_shape():
    assert len(CATALOG) == 8
    assert sum(p.currency == "USD" for p in CATALOG) == 5
    assert sum(p.currency == "EUR" for p in CATALOG) == 3
    assert len({p.sku for p in CATALOG}) == 8
    assert sum(p.sales for p in CATALOG if p.currency == "USD") >= 20


def test_loss_maker_really_loses_money_after_fees():
    p = next(p for p in CATALOG if p.sku == "EARBUDS-PRO")
    fee_estimate = p.selling_price * Decimal("0.0349") + Decimal("0.49")
    assert p.selling_price - fee_estimate - p.unit_cost - p.variable_cost_per_unit < 0


def test_select_products_filters_by_currency():
    assert {p.currency for p in select_products("EUR")} == {"EUR"}
    assert len(select_products("ALL")) == 8


def test_select_products_count_caps_total_sales():
    chosen = select_products("USD", count=7)
    assert sum(p.sales for p in chosen) == 7


def test_select_products_count_spreads_across_products():
    chosen = select_products("USD", count=5)
    assert len(chosen) == 5
    assert all(p.sales == 1 for p in chosen)
