import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from marginos.integrations.paypal.schemas import parse_capture, parse_refund

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_capture_reads_fee_and_custom_id():
    details = parse_capture(load("capture_completed.json"))

    assert details.capture_id == "CAP-TEST-001"
    assert details.status == "COMPLETED"
    assert details.gross == Decimal("29.99")
    assert details.currency == "USD"
    assert details.paypal_fee == Decimal("1.54")
    assert details.net == Decimal("28.45")
    assert details.custom_id == "EARBUDS-PRO"
    assert details.order_id == "ORD-TEST-001"
    assert details.captured_at == datetime(2026, 11, 11, 10, 0, 0, tzinfo=UTC)


def test_parse_capture_without_breakdown_has_none_fee():
    raw = load("capture_completed.json")
    del raw["seller_receivable_breakdown"]
    del raw["supplementary_data"]

    details = parse_capture(raw)

    assert details.paypal_fee is None
    assert details.net is None
    assert details.order_id is None
    assert details.raw is raw


def test_parse_refund_capture_id_from_up_link():
    result = parse_refund(load("refund_completed.json"))

    assert result.refund_id == "REF-TEST-001"
    assert result.status == "COMPLETED"
    assert result.amount == Decimal("5.00")
    assert result.currency == "USD"
    assert result.capture_id == "CAP-TEST-001"


def test_parse_refund_without_links_has_none_capture_id():
    raw = load("refund_completed.json")
    raw["links"] = []
    assert parse_refund(raw).capture_id is None
