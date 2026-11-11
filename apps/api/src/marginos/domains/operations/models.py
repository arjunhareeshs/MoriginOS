"""Operations ledger: PayPal orders, captures, refunds and invoices as the app observed them."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CHAR, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from marginos.core.db import Base
from marginos.domains.catalog.models import utcnow

MONEY = Numeric(18, 2)
CURRENCY = CHAR(3)


class Order(Base):
    __tablename__ = "paypal_order"

    id: Mapped[int] = mapped_column(primary_key=True)
    paypal_order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    currency: Mapped[str] = mapped_column(CURRENCY)
    buyer_email: Mapped[str | None] = mapped_column(String(320), default=None)
    custom_id: Mapped[str | None] = mapped_column(String(127), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    raw: Mapped[dict | None] = mapped_column(JSONB, default=None)

    captures: Mapped[list[Capture]] = relationship(back_populates="order")


class Capture(Base):
    __tablename__ = "capture"

    id: Mapped[int] = mapped_column(primary_key=True)
    paypal_capture_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("paypal_order.id", ondelete="SET NULL"), default=None
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("product.id", ondelete="SET NULL"), default=None, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    gross: Mapped[Decimal] = mapped_column(MONEY)
    paypal_fee: Mapped[Decimal | None] = mapped_column(MONEY, default=None)
    fee_known: Mapped[bool] = mapped_column(Boolean, default=False)
    net: Mapped[Decimal | None] = mapped_column(MONEY, default=None)
    currency: Mapped[str] = mapped_column(CURRENCY)
    status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    leakage: Mapped[bool] = mapped_column(Boolean, default=False)
    custom_id: Mapped[str | None] = mapped_column(String(127), default=None)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    source: Mapped[str] = mapped_column(String(16), default="api")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    raw: Mapped[dict | None] = mapped_column(JSONB, default=None)

    order: Mapped[Order | None] = relationship(back_populates="captures")
    refunds: Mapped[list[Refund]] = relationship(back_populates="capture")


class Refund(Base):
    __tablename__ = "refund"

    id: Mapped[int] = mapped_column(primary_key=True)
    paypal_refund_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    capture_id: Mapped[int] = mapped_column(
        ForeignKey("capture.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(CURRENCY)
    status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    source: Mapped[str] = mapped_column(String(16), default="api")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    raw: Mapped[dict | None] = mapped_column(JSONB, default=None)

    capture: Mapped[Capture] = relationship(back_populates="refunds")


class Invoice(Base):
    __tablename__ = "invoice"

    id: Mapped[int] = mapped_column(primary_key=True)
    paypal_invoice_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    total: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(CURRENCY)
    customer_email: Mapped[str | None] = mapped_column(String(320), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    raw: Mapped[dict | None] = mapped_column(JSONB, default=None)
