"""Catalog service: merchant bootstrap, product upsert, merchant-supplied costs and prices."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from marginos.core.config import get_settings
from marginos.core.money import q2, validate_currency
from marginos.domains.catalog.models import Merchant, Product, ProductCost


def ensure_merchant(db: Session) -> Merchant:
    merchant = db.scalar(select(Merchant).order_by(Merchant.id).limit(1))
    if merchant is not None:
        return merchant
    settings = get_settings()
    merchant = Merchant(
        name="Sandbox merchant",
        paypal_email=settings.paypal_merchant_email,
        currency_default="USD",
    )
    db.add(merchant)
    db.flush()
    return merchant


def get_product_by_sku(db: Session, sku: str) -> Product | None:
    return db.scalar(select(Product).where(Product.sku == sku))


def get_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise LookupError(f"product {product_id} not found")
    return product


def upsert_product(
    db: Session,
    *,
    sku: str,
    title: str,
    selling_price: Decimal,
    currency: str,
    description: str | None = None,
    image_url: str | None = None,
    source: str = "seed",
    channel3_id: str | None = None,
) -> Product:
    validate_currency(currency)
    if selling_price < 0:
        raise ValueError("selling_price must not be negative")
    product = get_product_by_sku(db, sku)
    if product is None:
        product = Product(sku=sku, currency=currency, selling_price=q2(selling_price), title=title)
        db.add(product)
    product.title = title
    product.selling_price = q2(selling_price)
    product.currency = currency
    product.description = description if description is not None else product.description
    product.image_url = image_url if image_url is not None else product.image_url
    product.source = source
    product.channel3_id = channel3_id if channel3_id is not None else product.channel3_id
    db.flush()
    return product


def set_cost(
    db: Session,
    product_id: int,
    *,
    unit_cost: Decimal,
    variable_cost_per_unit: Decimal | None,
    currency: str | None = None,
    label: str = "Sample data",
) -> ProductCost:
    product = get_product(db, product_id)
    if currency is not None and currency != product.currency:
        raise ValueError(
            f"cost currency {currency} does not match product currency {product.currency}"
        )
    if unit_cost < 0 or (variable_cost_per_unit is not None and variable_cost_per_unit < 0):
        raise ValueError("costs must not be negative")
    cost = ProductCost(
        product_id=product.id,
        unit_cost=q2(unit_cost),
        variable_cost_per_unit=q2(variable_cost_per_unit)
        if variable_cost_per_unit is not None
        else None,
        currency=product.currency,
        label=label,
    )
    db.add(cost)
    db.flush()
    return cost


def current_cost(db: Session, product_id: int) -> ProductCost | None:
    return db.scalar(
        select(ProductCost)
        .where(ProductCost.product_id == product_id)
        .order_by(ProductCost.effective_from.desc(), ProductCost.id.desc())
        .limit(1)
    )


def update_price(db: Session, product_id: int, selling_price: Decimal) -> Product:
    if selling_price < 0:
        raise ValueError("selling_price must not be negative")
    product = get_product(db, product_id)
    product.selling_price = q2(selling_price)
    db.flush()
    return product
