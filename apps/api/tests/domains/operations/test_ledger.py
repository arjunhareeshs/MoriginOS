from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from marginos.domains.catalog import service as catalog
from marginos.domains.operations import ledger
from marginos.domains.operations.models import Capture, Refund
from marginos.integrations.paypal.schemas import CaptureDetails, RefundResult


def _details(capture_id="CAP-1", sku="EARBUDS-PRO", fee="1.54", status="COMPLETED"):
    return CaptureDetails(
        capture_id=capture_id,
        status=status,
        gross=Decimal("29.99"),
        currency="USD",
        paypal_fee=Decimal(fee) if fee is not None else None,
        net=Decimal("28.45") if fee is not None else None,
        custom_id=sku,
        order_id="ORD-1",
        captured_at=datetime(2026, 11, 11, 10, 0, tzinfo=UTC),
        raw={"id": capture_id},
    )


def _refund(refund_id="REF-1", capture_id="CAP-1"):
    return RefundResult(
        refund_id=refund_id,
        status="COMPLETED",
        amount=Decimal("5.00"),
        currency="USD",
        capture_id=capture_id,
        raw={"id": refund_id},
    )


def test_record_capture_maps_sku_to_product(db):
    product = catalog.upsert_product(
        db, sku="EARBUDS-PRO", title="Earbuds", selling_price=Decimal("29.99"), currency="USD"
    )

    capture = ledger.record_capture(db, _details(), source="seed", quantity=2)

    assert capture.product_id == product.id
    assert capture.quantity == 2
    assert capture.gross == Decimal("29.99")
    assert capture.paypal_fee == Decimal("1.54")
    assert capture.fee_known is True
    assert capture.order.paypal_order_id == "ORD-1"


def test_record_capture_unknown_sku_keeps_row_unmapped(db):
    capture = ledger.record_capture(db, _details(sku="NOPE"), source="webhook")

    assert capture.product_id is None
    assert capture.paypal_capture_id == "CAP-1"


def test_record_capture_without_fee_sets_fee_known_false(db):
    capture = ledger.record_capture(db, _details(fee=None), source="webhook")
    assert capture.fee_known is False
    assert capture.paypal_fee is None


def test_record_capture_upsert_updates_status_not_duplicate(db):
    ledger.record_capture(db, _details(status="PENDING"), source="seed")
    ledger.record_capture(db, _details(status="COMPLETED"), source="webhook")

    rows = db.scalars(select(Capture).where(Capture.paypal_capture_id == "CAP-1")).all()

    assert len(rows) == 1
    assert rows[0].status == "COMPLETED"


def test_record_refund_creates_stub_capture_when_missing(db):
    refund = ledger.record_refund(db, _refund(capture_id="CAP-MISSING"), source="webhook")

    stub = db.scalar(select(Capture).where(Capture.paypal_capture_id == "CAP-MISSING"))
    assert stub is not None
    assert stub.source == "webhook"
    assert stub.status == "UNKNOWN"
    assert refund.capture_id == stub.id
    assert refund.amount == Decimal("5.00")


def test_record_refund_is_idempotent_on_refund_id(db):
    ledger.record_capture(db, _details(), source="seed")
    ledger.record_refund(db, _refund(), source="api", reason="first")
    ledger.record_refund(db, _refund(), source="webhook")

    rows = db.scalars(select(Refund).where(Refund.paypal_refund_id == "REF-1")).all()

    assert len(rows) == 1
    assert rows[0].reason == "first"
    assert rows[0].source == "webhook"


def test_set_capture_status_marks_leakage(db):
    ledger.record_capture(db, _details(), source="seed")

    capture = ledger.set_capture_status(db, "CAP-1", "REVERSED", leakage=True)

    assert capture.status == "REVERSED"
    assert capture.leakage is True


def test_capture_for_order_finds_by_paypal_order_id(db):
    ledger.record_capture(db, _details(), source="seed")
    assert ledger.capture_for_order(db, "ORD-1").paypal_capture_id == "CAP-1"
    assert ledger.capture_for_order(db, "ORD-404") is None
