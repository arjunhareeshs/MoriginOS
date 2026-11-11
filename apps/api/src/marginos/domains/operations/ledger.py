"""Ledger writes. Every function is an idempotent upsert keyed by the PayPal ID."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from marginos.domains.catalog.models import Product
from marginos.domains.operations.models import Capture, Order, Refund
from marginos.integrations.paypal.schemas import CaptureDetails, RefundResult


def _get_or_create_order(
    db: Session, paypal_order_id: str, *, currency: str, custom_id: str | None
) -> Order:
    order = db.scalar(select(Order).where(Order.paypal_order_id == paypal_order_id))
    if order is None:
        order = Order(paypal_order_id=paypal_order_id, currency=currency, custom_id=custom_id)
        db.add(order)
        db.flush()
    return order


def _product_id_for_sku(db: Session, sku: str | None) -> int | None:
    if not sku:
        return None
    return db.scalar(select(Product.id).where(Product.sku == sku))


def record_capture(
    db: Session, details: CaptureDetails, *, source: str, quantity: int = 1
) -> Capture:
    capture = db.scalar(select(Capture).where(Capture.paypal_capture_id == details.capture_id))
    if capture is None:
        capture = Capture(
            paypal_capture_id=details.capture_id, gross=details.gross, currency=details.currency
        )
        db.add(capture)
        capture.quantity = quantity
    capture.status = details.status
    capture.gross = details.gross
    capture.currency = details.currency or capture.currency
    if details.paypal_fee is not None:
        capture.paypal_fee = details.paypal_fee
        capture.net = details.net
        capture.fee_known = True
    capture.custom_id = details.custom_id or capture.custom_id
    if capture.product_id is None:
        capture.product_id = _product_id_for_sku(db, capture.custom_id)
    if details.order_id and capture.order_id is None:
        capture.order = _get_or_create_order(
            db, details.order_id, currency=details.currency, custom_id=details.custom_id
        )
    capture.captured_at = details.captured_at or capture.captured_at
    capture.source = source
    capture.raw = details.raw
    db.flush()
    return capture


def _stub_capture(db: Session, paypal_capture_id: str, currency: str) -> Capture:
    capture = Capture(
        paypal_capture_id=paypal_capture_id,
        gross=0,
        currency=currency,
        status="UNKNOWN",
        source="webhook",
    )
    db.add(capture)
    db.flush()
    return capture


def record_refund(
    db: Session, result: RefundResult, *, source: str, reason: str | None = None
) -> Refund:
    refund = db.scalar(select(Refund).where(Refund.paypal_refund_id == result.refund_id))
    if refund is None:
        if result.capture_id is None:
            raise ValueError(f"refund {result.refund_id} has no capture reference")
        capture = db.scalar(select(Capture).where(Capture.paypal_capture_id == result.capture_id))
        if capture is None:
            capture = _stub_capture(db, result.capture_id, result.currency)
        refund = Refund(
            paypal_refund_id=result.refund_id,
            capture_id=capture.id,
            amount=result.amount,
            currency=result.currency,
            reason=reason,
        )
        db.add(refund)
    refund.status = result.status
    refund.amount = result.amount
    refund.source = source
    refund.raw = result.raw
    if reason and not refund.reason:
        refund.reason = reason
    db.flush()
    return refund


def set_capture_status(
    db: Session, paypal_capture_id: str, status: str, *, leakage: bool = False
) -> Capture:
    capture = db.scalar(select(Capture).where(Capture.paypal_capture_id == paypal_capture_id))
    if capture is None:
        capture = _stub_capture(db, paypal_capture_id, "")
    capture.status = status
    if leakage:
        capture.leakage = True
    db.flush()
    return capture


def capture_for_order(db: Session, paypal_order_id: str) -> Capture | None:
    return db.scalar(
        select(Capture)
        .join(Order, Capture.order_id == Order.id)
        .where(Order.paypal_order_id == paypal_order_id)
        .order_by(Capture.id.desc())
        .limit(1)
    )
