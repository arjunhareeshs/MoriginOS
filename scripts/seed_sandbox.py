"""Seed the PayPal sandbox with orders and captures and record them in the local ledger.

Usage (from apps/api, with .env filled in and the database migrated):
    python ../../scripts/seed_sandbox.py --currency USD --strategy card
    python ../../scripts/seed_sandbox.py --currency EUR --strategy links --count 9

Strategies:
    card   create orders with a sandbox test card; COMPLETED orders return the capture directly.
    links  create PayPal-funded orders, print approve links, wait for Enter, then capture.

Prints status codes and PayPal debug_ids on failure. Never prints tokens or secrets.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
import uuid
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed_data import CATALOG, SeedProduct  # noqa: E402

from marginos.core.config import get_settings  # noqa: E402
from marginos.core.db import session_scope  # noqa: E402
from marginos.domains.catalog import service as catalog  # noqa: E402
from marginos.domains.operations.ledger import record_capture, record_refund  # noqa: E402
from marginos.integrations.paypal import orders, payments  # noqa: E402
from marginos.integrations.paypal.client import PayPalClient, get_paypal_client  # noqa: E402
from marginos.integrations.paypal.errors import PayPalError  # noqa: E402
from marginos.integrations.paypal.schemas import CaptureDetails  # noqa: E402

TEST_CARD = {
    "number": "4111111111111111",
    "expiry": "2030-12",
    "name": "Sandbox Buyer",
    "billing_address": {
        "address_line_1": "123 Main St",
        "admin_area_2": "San Jose",
        "admin_area_1": "CA",
        "postal_code": "95131",
        "country_code": "US",
    },
}


def select_products(currency: str, count: int | None = None) -> list[SeedProduct]:
    """Products for the chosen currency, optionally trimmed so total sales equal `count`."""
    chosen = [p for p in CATALOG if currency == "ALL" or p.currency == currency]
    if count is None:
        return chosen
    # Round-robin so a small --count still touches every product.
    sales = {p.sku: 0 for p in chosen}
    remaining = count
    while remaining > 0 and any(sales[p.sku] < p.sales for p in chosen):
        for product in chosen:
            if remaining > 0 and sales[product.sku] < product.sales:
                sales[product.sku] += 1
                remaining -= 1
    return [
        dataclasses.replace(p, sales=sales[p.sku], refunds=min(p.refunds, sales[p.sku]))
        for p in chosen
        if sales[p.sku] > 0
    ]


def _fail(action: str, error: PayPalError) -> None:
    print(f"  ! {action} failed: status={error.status_code} debug_id={error.debug_id or '-'}")


def _create_and_capture(
    client: PayPalClient, product: SeedProduct, strategy: str, run_id: str, n: int
) -> CaptureDetails | None:
    settings = get_settings()
    request_id = f"seed-{run_id}-{product.sku}-{n}"
    try:
        order = orders.create_order(
            client,
            currency=product.currency,
            sku=product.sku,
            title=product.title,
            quantity=1,
            unit_price=product.selling_price,
            payment_source={"card": TEST_CARD} if strategy == "card" else None,
            return_url=settings.web_base_url,
            cancel_url=settings.web_base_url,
            request_id=request_id,
        )
        if strategy == "links":
            approve = next(
                (
                    link["href"]
                    for link in order.get("links", [])
                    if link.get("rel") in ("payer-action", "approve")
                ),
                None,
            )
            print(f"  Approve as the sandbox buyer: {approve}")
            input("  Press Enter after approving... ")
        captures = orders.captures_from_order(order)
        if not captures:
            captures = orders.capture_order(client, order["id"], request_id=f"{request_id}-cap")
    except PayPalError as error:
        _fail(f"{product.sku} order", error)
        return None
    if not captures:
        print(f"  ! {product.sku}: no capture returned (order status {order.get('status')})")
        return None
    capture = captures[0]
    if capture.paypal_fee is None:
        capture = payments.get_capture(client, capture.capture_id)
    return capture


def seed(currency: str, strategy: str, count: int | None) -> dict[str, dict[str, int]]:
    client = get_paypal_client()
    run_id = uuid.uuid4().hex[:8]
    summary: dict[str, dict[str, int]] = defaultdict(
        lambda: {"captures": 0, "fee_known": 0, "refunds": 0}
    )
    with session_scope() as db:
        catalog.ensure_merchant(db)
        for product in select_products(currency, count):
            row = catalog.upsert_product(
                db,
                sku=product.sku,
                title=product.title,
                description=product.description,
                selling_price=product.selling_price,
                currency=product.currency,
            )
            if catalog.current_cost(db, row.id) is None:
                catalog.set_cost(
                    db,
                    row.id,
                    unit_cost=product.unit_cost,
                    variable_cost_per_unit=product.variable_cost_per_unit,
                )
            print(f"{product.sku} ({product.currency}): {product.sales} sales")
            recorded = []
            for n in range(product.sales):
                details = _create_and_capture(client, product, strategy, run_id, n)
                if details is None:
                    continue
                record_capture(db, details, source="seed")
                db.commit()
                recorded.append(details)
                stats = summary[product.currency]
                stats["captures"] += 1
                stats["fee_known"] += int(details.paypal_fee is not None)
            for details in recorded[len(recorded) - product.refunds :] if product.refunds else []:
                try:
                    result = payments.refund_capture(
                        client,
                        details.capture_id,
                        amount=None,
                        currency=product.currency,
                        note="Seed: customer return",
                        request_id=f"seed-{details.capture_id}",
                    )
                except PayPalError as error:
                    _fail(f"{product.sku} refund", error)
                    continue
                record_refund(db, result, source="seed", reason="Seed: customer return")
                db.commit()
                summary[product.currency]["refunds"] += 1
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--currency", choices=["USD", "EUR", "ALL"], default="USD")
    parser.add_argument("--strategy", choices=["card", "links"], default="card")
    parser.add_argument("--count", type=int, default=None, help="cap total sales")
    args = parser.parse_args(argv)
    summary = seed(args.currency, args.strategy, args.count)
    if not summary:
        print("No captures recorded. Check the errors above.")
        return 1
    for currency, stats in sorted(summary.items()):
        print(
            f"{currency}: captures={stats['captures']} "
            f"fee_known={stats['fee_known']} refunds={stats['refunds']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
