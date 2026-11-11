"""Catalog: merchant, products, merchant-supplied costs and the Channel3 result cache."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import CHAR, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from marginos.core.db import Base

MONEY = Numeric(18, 2)
CURRENCY = CHAR(3)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Merchant(Base):
    __tablename__ = "merchant"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    paypal_email: Mapped[str] = mapped_column(String(320), default="")
    currency_default: Mapped[str] = mapped_column(CURRENCY, default="USD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )


class Product(Base):
    __tablename__ = "product"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    image_url: Mapped[str | None] = mapped_column(Text, default=None)
    selling_price: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(CURRENCY)
    source: Mapped[str] = mapped_column(String(32), default="seed")
    channel3_id: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )

    costs: Mapped[list[ProductCost]] = relationship(
        back_populates="product", order_by="desc(ProductCost.effective_from)"
    )


class ProductCost(Base):
    __tablename__ = "product_cost"
    __table_args__ = (Index("ix_product_cost_product_effective", "product_id", "effective_from"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id", ondelete="CASCADE"))
    unit_cost: Mapped[Decimal] = mapped_column(MONEY)
    variable_cost_per_unit: Mapped[Decimal | None] = mapped_column(MONEY, default=None)
    currency: Mapped[str] = mapped_column(CURRENCY)
    label: Mapped[str] = mapped_column(String(64), default="Sample data")
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    product: Mapped[Product] = relationship(back_populates="costs")


class Channel3Cache(Base):
    __tablename__ = "channel3_cache"

    query_key: Mapped[str] = mapped_column(String(512), primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    results: Mapped[list] = mapped_column(JSONB)
