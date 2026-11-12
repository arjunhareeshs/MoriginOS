# Module: sandbox seed (Block 2, Task 7)

## Purpose
Create real PayPal sandbox orders and captures, and record them in the local ledger, so the
Transactions, Products and margin screens have genuine data (fee and net come from PayPal's
capture response, not from estimates). Seeding early matters: Transaction Search can lag by up
to 3 hours.

## Files
| File | Role |
|---|---|
| `scripts/seed_data.py` | `CATALOG`: 8 products (5 USD, 3 EUR), costs labelled "Sample data". `EARBUDS-PRO` is the designed loss-maker (cost 27.50 + 1.50 variable on a 29.99 price). |
| `scripts/seed_sandbox.py` | CLI. Upserts merchant, products and costs, creates orders, records captures, refunds the last N captures of products with `refunds > 0`. |
| `apps/api/tests/scripts/test_seed_data.py` | Catalog invariants and `select_products` behaviour. No network. |

## Design
- Reuses the adapters (`orders`, `payments`) and ledger (`record_capture`, `record_refund`);
  the script contains no HTTP of its own (architecture rule 1).
- Idempotency: order requests use `PayPal-Request-Id = seed-<run>-<sku>-<n>`; refunds use
  `seed-<capture_id>`, so a retried refund cannot double-refund. Each run gets a new run id, so
  re-running creates new orders by design.
- Ledger writes are upserts keyed by PayPal IDs and committed per capture, so a mid-run failure
  keeps what was already recorded.
- If an order response lacks fee data, the script re-reads the capture via `get_capture`.
- Failures print HTTP status and `debug_id` only. Credentials are never printed.

## Usage (from `apps/api`)
```
python ../../scripts/seed_sandbox.py --currency USD --strategy card
python ../../scripts/seed_sandbox.py --currency EUR --strategy card
python ../../scripts/seed_sandbox.py --strategy links --count 10
```
Expected end of output: `USD: captures=21 fee_known=21 refunds=1`.

## Strategies
- `card`: test card in `payment_source`; no buyer interaction. May be rejected if the sandbox app
  lacks card processing.
- `links`: prints PayPal approve links, waits for Enter, then captures. Slower, always works.
- The Playwright-automated PayPal strategy from the plan is deferred; add it only if both of the
  above fail.

## Known limits
- Fixtures in `tests/integrations/paypal/fixtures` are still hand-written; replace them with
  sanitised real responses after the first real run (plan Task 7, step 7).
- EUR requires the sandbox merchant to accept EUR; if not, EUR is skipped and the UI stays
  per-currency.
