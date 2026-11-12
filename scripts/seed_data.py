"""Sandbox catalog used by seed_sandbox.py.

Prices are real selling prices; costs are labelled "Sample data" in the app (merchant-supplied
costs are not available from PayPal). EARBUDS-PRO is the designed loss-maker: its cost plus
PayPal's fee exceeds the selling price, so it ranks lowest on margin in the demo.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from marginos.core.money import validate_currency


@dataclass(frozen=True)
class SeedProduct:
    sku: str
    title: str
    description: str
    selling_price: Decimal
    currency: str
    unit_cost: Decimal
    variable_cost_per_unit: Decimal
    sales: int
    refunds: int = 0


def _p(
    sku: str,
    title: str,
    description: str,
    price: str,
    currency: str,
    cost: str,
    variable: str,
    sales: int,
    refunds: int = 0,
) -> SeedProduct:
    return SeedProduct(
        sku=sku,
        title=title,
        description=description,
        selling_price=Decimal(price),
        currency=currency,
        unit_cost=Decimal(cost),
        variable_cost_per_unit=Decimal(variable),
        sales=sales,
        refunds=refunds,
    )


CATALOG: list[SeedProduct] = [
    # USD (5 products, 21 sales)
    _p("EARBUDS-PRO", "Wireless Earbuds Pro", "Bluetooth 5.3 earbuds with charging case",
       "29.99", "USD", "27.50", "1.50", 5, 1),
    _p("MUG-CERAMIC", "Ceramic Travel Mug", "350 ml insulated ceramic mug",
       "18.00", "USD", "6.20", "0.80", 4),
    _p("TOTE-CANVAS", "Canvas Tote Bag", "Heavy cotton tote, natural",
       "24.00", "USD", "8.90", "0.60", 4),
    _p("NOTEBOOK-A5", "A5 Dotted Notebook", "160 pages, hardcover",
       "14.50", "USD", "4.10", "0.40", 4),
    _p("CASE-PHONE", "Slim Phone Case", "Shock-absorbing polycarbonate case",
       "19.99", "USD", "7.30", "0.70", 4),
    # EUR (3 products, 9 sales)
    _p("LAMP-DESK", "LED Desk Lamp", "Dimmable lamp with USB port",
       "39.00", "EUR", "17.50", "1.20", 3),
    _p("BOTTLE-STEEL", "Steel Water Bottle", "750 ml vacuum insulated",
       "22.00", "EUR", "8.40", "0.90", 3),
    _p("CABLE-USBC", "USB-C Cable 2m", "Braided 100 W charging cable",
       "12.50", "EUR", "3.20", "0.30", 3),
]

for _product in CATALOG:
    validate_currency(_product.currency)
