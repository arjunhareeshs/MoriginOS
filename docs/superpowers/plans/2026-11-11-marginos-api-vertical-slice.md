# MarginOS API Vertical Slice (Blocks 0 to 7) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reach Checkpoint A: a refund requested by the AI, approved by the merchant, executed on PayPal sandbox and verified by a signature-checked webhook (or API poll), with seeded captures, deterministic margins and Channel3 discovery all available through the API.

**Architecture:** One FastAPI service with sync SQLAlchemy 2 on Postgres. `integrations/` wraps PayPal, Channel3 and an OpenAI-compatible LLM with httpx; `domains/` hold models and services; `orchestrator/` runs a tool-calling loop whose side-effect tools only create approvals. An in-process event bus feeds a Server-Sent Events endpoint.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2, Alembic, psycopg 3, pydantic-settings, httpx, openai (client only, pointed at any OpenAI-compatible base URL), pytest, respx, pytest-cov, ruff, Docker Postgres 16.

**Spec:** `docs/superpowers/specs/2026-11-11-marginos-hackathon-solution-design.md`

## Global Constraints

- Secrets only in repo-root `.env` (gitignored) and Render env vars; `apps/env.example` holds placeholders only; no secret value is ever logged or printed.
- Every amount is `Decimal` quantised to 2 places plus an ISO 4217 code; never sum across currencies.
- `domains/finance` imports nothing from `integrations/` or `orchestrator/`.
- Only `integrations/` makes HTTP calls. Domains call adapters; tools call services.
- Every PayPal write sends `PayPal-Request-Id`; refunds use the approval ID.
- Webhook verification is real (postback). `PAYPAL_WEBHOOK_SKIP_VERIFY` is refused when `APP_ENV=production`.
- Task states: `planned`, `awaiting_approval`, `executing`, `awaiting_verification`, `verified`, `failed`, `rejected`. Only `domains/approvals/service.py` changes them.
- No mock data is used to claim an integration works. Each integration task ends with a real sandbox call whose output is shown.
- Timestamps are `timestamptz` in UTC. Money columns are `Numeric(18, 2)` with `currency CHAR(3)`.
- Commit after every task with `<type>: <description>` and the attribution trailer from the session.

## Review Focus

1. A `PAYMENT.CAPTURE.REFUNDED` webhook that arrives before the app stored the refund or even the capture must create stub rows and still verify the task later (test in Task 11).
2. Double-clicking Approve must execute exactly one PayPal refund and return the same result both times (test in Task 20).
3. A refund larger than the remaining capturable amount must put the task in `failed` with the PayPal error body stored, never raise a 500 (test in Task 20).
4. The per-currency summary must never add USD and EUR; a mixed ledger yields two rows (test in Task 14).
5. An LLM reply that states an amount absent from tool results must be rejected by the post-check (test in Task 24).

---

### Task 1: Security and repository hygiene (Block 0)

**Files:**
- Modify: `apps/env.example`
- Create: `.gitignore`, `LICENSE`, `README.md` (rewrite, UTF-8)
- Create: `scripts/check_old_credentials.py` (throwaway verification, reads the committed file from git history, prints only HTTP status codes)

**Interfaces:**
- Produces: a clean `apps/env.example` whose keys are the contract for `Settings` in Task 2.

- [ ] **Step 1: Confirm the exposed credentials are dead**

Run: `python -I scripts/check_old_credentials.py` which does `git show e3d1736:apps/env.example`, extracts the PayPal pair and the Channel3 key into local variables, calls `POST {PAYPAL_API_BASE}/v1/oauth2/token` and `POST https://api.trychannel3.com/v1/search` and prints only `paypal_status=<code> channel3_status=<code>`.
Expected: `paypal_status=401 channel3_status=401` (or 403). If either returns 200, STOP and tell the owner rotation is incomplete. Delete the script after use.

- [ ] **Step 2: Scrub `apps/env.example`**

Replace every real value with an empty placeholder. Keep every key name. Add `PAYPAL_WEBHOOK_SKIP_VERIFY=false`, `PAYPAL_BUYER_US_EMAIL=`, `PAYPAL_BUYER_US_PASSWORD=`, `PAYPAL_BUYER_EU_EMAIL=`, `PAYPAL_BUYER_EU_PASSWORD=`, `LLM_BASE_URL_OVERRIDE=`.

- [ ] **Step 3: Add `.gitignore`**

Entries: `.env`, `.env.*`, `!.env.example`, `*.local`, `node_modules/`, `.venv/`, `__pycache__/`, `*.pyc`, `dist/`, `.pytest_cache/`, `.ruff_cache/`, `htmlcov/`, `.coverage`, `apps/web/dist/`, `playwright-report/`, `test-results/`.

- [ ] **Step 4: Add MIT `LICENSE` and a UTF-8 `README.md`**

README sections: what MarginOS is (two sentences), status (hackathon build in progress), local run (placeholder commands filled in Task 2), security note (sandbox only, single merchant). Write with `Out-File -Encoding utf8` or the Write tool; verify with `file README.md` showing UTF-8.

- [ ] **Step 5: Verify no credential remains**

Run: `git grep -nE "PAYPAL_CLIENT_SECRET=|CHANNEL3_API_KEY=" -- apps/env.example`
Expected: both lines end with `=` and nothing else.

- [ ] **Step 6: Commit**

```bash
git add .gitignore LICENSE README.md apps/env.example
git commit -m "chore: remove credentials from env example, add license and gitignore"
```

---

### Task 2: API scaffold, settings, database, money helpers (Block 1)

**Files:**
- Create: `apps/api/pyproject.toml`, `apps/api/alembic.ini`, `apps/api/migrations/env.py`, `apps/api/migrations/script.py.mako`
- Create: `apps/api/src/marginos/__init__.py`, `main.py`, `core/__init__.py`, `core/config.py`, `core/db.py`, `core/money.py`, `core/logging.py`
- Create: `docker-compose.yml` (repo root; Postgres 16, db `marginos`, user/password `marginos`, port 5432; second db `marginos_test` created by an init script `scripts/db/init.sql`)
- Create: `apps/api/tests/conftest.py`, `apps/api/tests/core/test_config.py`, `apps/api/tests/core/test_money.py`, `apps/api/tests/test_health.py`

**Interfaces:**
- Produces: `get_settings() -> Settings` (fields named exactly as the env keys, lower-cased); `Base`, `SessionLocal`, `get_db()` FastAPI dependency, `session_scope()` context manager in `core/db.py`; `D(value: str | int | float | Decimal) -> Decimal`, `q2(d: Decimal) -> Decimal` (ROUND_HALF_UP), `validate_currency(code: str) -> str` in `core/money.py`; `create_app() -> FastAPI` in `main.py`; test fixtures `db` (transactional session on `marginos_test`) and `client` (TestClient with `get_db` overridden).

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_config.py
def test_production_refuses_skip_verify(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production"); monkeypatch.setenv("PAYPAL_WEBHOOK_SKIP_VERIFY", "true")
    with pytest.raises(ValueError): Settings(_env_file=None)

def test_settings_never_repr_secret(monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "abc-secret")
    assert "abc-secret" not in repr(Settings(_env_file=None))

# tests/core/test_money.py
def test_q2_rounds_half_up(): assert q2(D("1.005")) == Decimal("1.01")
def test_validate_currency_rejects_lowercase(): with pytest.raises(ValueError): validate_currency("usd")

# tests/test_health.py
def test_health(client): assert client.get("/health").json() == {"status": "ok", "env": "development"}
```

- [ ] **Step 2: Run tests, expect ImportError / 404**

Run: `cd apps/api && pytest -q`

- [ ] **Step 3: Implement**

`pyproject.toml`: project `marginos`, `requires-python = ">=3.13"`, deps: fastapi, uvicorn[standard], sqlalchemy>=2.0, alembic, psycopg[binary], pydantic-settings, httpx, openai, python-multipart; dev: pytest, pytest-cov, respx, ruff, httpx. `[tool.pytest.ini_options] pythonpath = ["src"]`. `[tool.ruff] line-length = 100`.
`Settings`: `SecretStr` for every `*_secret`, `*_api_key`, `*_password`; `env_file` resolved as `Path(__file__).resolve().parents[5] / ".env"`; model validator for the production rule.
`db.py`: engine from `settings.database_url`, `pool_pre_ping=True`.
`main.py`: `create_app()` registers CORS for `settings.web_base_url` only, `/health`, and lifespan that logs startup without secrets. `app = create_app()`.
`conftest.py`: `TEST_DATABASE_URL = settings.database_url.replace("/marginos", "/marginos_test")`; session fixture creates all tables once, each test runs in a rolled-back transaction.
Alembic `env.py` imports `Base` and sets `target_metadata`, URL from settings.

- [ ] **Step 4: Start Postgres and run tests**

Run: `docker compose up -d db` then `cd apps/api && pytest -q`
Expected: 5 passed.

- [ ] **Step 5: Run the server once**

Run: `cd apps/api && uvicorn marginos.main:app --port 8000` and `curl -s localhost:8000/health`
Expected: `{"status":"ok","env":"development"}`.

- [ ] **Step 6: Update README run instructions and commit**

```bash
git add docker-compose.yml scripts/db apps/api README.md
git commit -m "feat: scaffold FastAPI service with settings, db, money helpers"
```

---

### Task 3: Catalog models and migration (Block 1)

**Files:**
- Create: `apps/api/src/marginos/domains/catalog/__init__.py`, `models.py`, `schemas.py`, `service.py`
- Create: `apps/api/migrations/versions/0001_catalog.py` (autogenerated, then reviewed)
- Test: `apps/api/tests/domains/catalog/test_service.py`

**Interfaces:**
- Produces: models `Merchant(id, name, paypal_email, currency_default)`, `Product(id, sku unique, title, description, image_url, selling_price, currency, source, channel3_id, created_at)`, `ProductCost(id, product_id, unit_cost, variable_cost_per_unit, currency, label default "Sample data", effective_from)`, `Channel3Cache(query_key pk, fetched_at, results JSONB)`.
- Service: `ensure_merchant(db) -> Merchant` (from settings), `get_product_by_sku(db, sku) -> Product | None`, `upsert_product(db, *, sku, title, selling_price, currency, description=None, image_url=None, source="seed", channel3_id=None) -> Product`, `set_cost(db, product_id, *, unit_cost: Decimal, variable_cost_per_unit: Decimal | None) -> ProductCost`, `current_cost(db, product_id) -> ProductCost | None`, `update_price(db, product_id, selling_price: Decimal) -> Product`.

- [ ] **Step 1: Write failing tests**

```python
def test_set_cost_creates_new_row_and_current_cost_returns_latest(db): ...  # two set_cost calls, current_cost is the second
def test_upsert_product_is_idempotent_on_sku(db): ...  # same sku twice -> one row, title updated
def test_cost_currency_must_match_product(db): with pytest.raises(ValueError): ...
```

- [ ] **Step 2: Run, expect failure** `pytest tests/domains/catalog -q`

- [ ] **Step 3: Implement models and service; generate migration**

Run: `alembic revision --autogenerate -m "catalog"` then `alembic upgrade head`. Review the file: Numeric(18,2), CHAR(3), JSONB.

- [ ] **Step 4: Run tests, expect pass**

- [ ] **Step 5: Commit** `git commit -m "feat: catalog models, costs and initial migration"`

---

### Task 4: PayPal client with token cache (Block 2)

**Files:**
- Create: `apps/api/src/marginos/integrations/__init__.py`, `integrations/paypal/__init__.py`, `client.py`, `errors.py`
- Test: `apps/api/tests/integrations/paypal/test_client.py`

**Interfaces:**
- Produces: `class PayPalClient(base_url: str, client_id: str, client_secret: str, http: httpx.Client | None = None, clock: Callable[[], float] = time.monotonic)` with `token() -> str` and `request(method: str, path: str, *, json: dict | None = None, params: dict | None = None, request_id: str | None = None) -> dict`; `class PayPalError(Exception)` with `status_code: int`, `body: dict | str`, `debug_id: str | None`; `get_paypal_client() -> PayPalClient` cached from settings.

- [ ] **Step 1: Write failing tests (respx)**

```python
def test_token_cached_until_expiry(respx_mock): ...        # two requests, one token call
def test_token_refreshed_after_expiry(respx_mock): ...     # clock advanced past expires_in-60
def test_request_sets_request_id_header(respx_mock): ...   # PayPal-Request-Id == given
def test_error_raises_paypal_error_with_debug_id(respx_mock): ...  # 422 body -> PayPalError.status_code == 422
```

- [ ] **Step 2: Run, expect ImportError**

- [ ] **Step 3: Implement** (token via `POST /v1/oauth2/token` with basic auth and `grant_type=client_credentials`; cache until `expires_in - 60`; never log the token or secret).

- [ ] **Step 4: Run tests, expect pass**

- [ ] **Step 5: Real call**

Run: `python -c "from marginos.integrations.paypal.client import get_paypal_client as g; c=g(); print('token_len', len(c.token()))"`
Expected: `token_len` greater than 0. If 401: STOP, report that the new credentials are not in `.env`.

- [ ] **Step 6: Commit** `git commit -m "feat: PayPal client with cached client-credentials token"`

---

### Task 5: PayPal orders, payments and webhook adapters (Block 2)

**Files:**
- Create: `integrations/paypal/schemas.py`, `orders.py`, `payments.py`, `webhooks.py`
- Test: `tests/integrations/paypal/test_schemas.py`, `test_payments.py`, `test_webhooks.py`, fixtures in `tests/integrations/paypal/fixtures/*.json` (hand-written from the PayPal reference shapes; replaced by real sandbox responses once Task 8 runs)

**Interfaces:**
- Produces:
  - `CaptureDetails(capture_id, status, gross: Decimal, currency, paypal_fee: Decimal | None, net: Decimal | None, custom_id: str | None, order_id: str | None, captured_at: datetime | None, raw: dict)`; `parse_capture(raw: dict) -> CaptureDetails`.
  - `RefundResult(refund_id, status, amount: Decimal, currency, capture_id: str | None, raw: dict)`; `parse_refund(raw: dict) -> RefundResult` (capture ID from the `links` entry with `rel == "up"`).
  - `create_order(client, *, currency, sku, title, quantity, unit_price: Decimal, payment_source: dict | None, return_url, cancel_url, request_id) -> dict` (sets `purchase_units[0].custom_id = sku`, `items[0]`, `amount.breakdown.item_total`).
  - `get_order(client, order_id) -> dict`, `capture_order(client, order_id, request_id) -> list[CaptureDetails]`.
  - `get_capture(client, capture_id) -> CaptureDetails`, `refund_capture(client, capture_id, *, amount: Decimal | None, currency, note, request_id) -> RefundResult` (omit `amount` for a full refund), `get_refund(client, refund_id) -> RefundResult`.
  - `verify_signature(client, headers: Mapping[str, str], raw_body: bytes, webhook_id: str) -> bool` (posts `webhook_event` as the parsed JSON of the raw bytes with no re-ordering: use `json.loads(raw_body)` and send with `httpx` `content=` of a hand-built body where `webhook_event` is spliced in as the raw bytes).
  - `WEBHOOK_EVENT_TYPES: list[str]` (the eleven types in spec 3.4), `ensure_webhook(client, url: str, event_types: list[str]) -> str` (list, patch if a webhook with our URL exists, else create; returns ID).

- [ ] **Step 1: Write failing tests**

```python
def test_parse_capture_reads_fee_and_custom_id(): d = parse_capture(load("capture_completed.json")); assert d.paypal_fee == Decimal("1.54") and d.custom_id == "EARBUDS-PRO"
def test_parse_capture_without_breakdown_has_none_fee(): ...
def test_parse_refund_capture_id_from_up_link(): ...
def test_refund_capture_full_omits_amount(respx_mock): ...   # request json has no "amount"
def test_verify_signature_sends_raw_event_bytes(respx_mock): ... # body contains the exact raw bytes substring
def test_ensure_webhook_patches_existing(respx_mock): ...
```

- [ ] **Step 2: Run, expect failure**

- [ ] **Step 3: Implement the four modules**

- [ ] **Step 4: Run tests, expect pass**

- [ ] **Step 5: Commit** `git commit -m "feat: PayPal orders, payments and webhook adapters"`

---

### Task 6: Operations models and ledger service (Block 2)

**Files:**
- Create: `domains/operations/__init__.py`, `models.py`, `schemas.py`, `ledger.py`
- Create: `migrations/versions/0002_operations.py`
- Test: `tests/domains/operations/test_ledger.py`

**Interfaces:**
- Produces: models `Order(id, paypal_order_id unique, status, currency, buyer_email, custom_id, created_at, raw)`, `Capture(id, paypal_capture_id unique, order_id FK nullable, product_id FK nullable, quantity, gross, paypal_fee nullable, fee_known bool, net nullable, currency, status, leakage bool default false, captured_at, source, raw)`, `Refund(id, paypal_refund_id unique, capture_id FK, amount, currency, status, reason, created_at, source, raw)`, `Invoice(...)` per spec.
- Service `ledger.py`: `record_capture(db, details: CaptureDetails, *, source: str, quantity: int = 1) -> Capture` (upsert; maps `custom_id` to `Product.sku`; `fee_known = details.paypal_fee is not None`), `record_refund(db, result: RefundResult, *, source: str, reason: str | None = None) -> Refund` (creates a stub `Capture(source="webhook", status="UNKNOWN")` when the capture is unknown), `set_capture_status(db, paypal_capture_id: str, status: str, *, leakage: bool = False) -> Capture`, `capture_for_order(db, paypal_order_id: str) -> Capture | None`.

- [ ] **Step 1: Write failing tests**

```python
def test_record_capture_maps_sku_to_product(db): ...
def test_record_capture_unknown_sku_keeps_row_unmapped(db): ...   # product_id is None
def test_record_capture_upsert_updates_status_not_duplicate(db): ...
def test_record_refund_creates_stub_capture_when_missing(db): ...
def test_record_refund_is_idempotent_on_refund_id(db): ...
```

- [ ] **Step 2: Run, expect failure** — **Step 3: Implement, autogenerate migration, upgrade** — **Step 4: Run tests, expect pass**

- [ ] **Step 5: Commit** `git commit -m "feat: operations ledger models and upsert services"`

---

### Task 7: Seed script and first real captures (Block 2)

**Files:**
- Create: `scripts/seed_sandbox.py`, `scripts/seed_data.py` (catalog definition), `scripts/approve_orders_playwright.py` (fallback)
- Test: `tests/scripts/test_seed_data.py`

**Interfaces:**
- Consumes: Task 3 catalog service, Task 5 orders/payments, Task 6 ledger.
- Produces: `CATALOG: list[SeedProduct(sku, title, description, selling_price, currency, unit_cost, variable_cost_per_unit, sales: int, refunds: int)]` with 8 products (5 USD, 3 EUR) where `EARBUDS-PRO` (USD 29.99, cost 27.50, 5 sales, 1 refund) is the designed loss-maker; CLI `python scripts/seed_sandbox.py --count N --currency USD|EUR|ALL --strategy card|paypal|links`.

- [ ] **Step 1: Write failing test**

```python
def test_seed_catalog_has_one_designed_loss_maker():
    losers = [p for p in CATALOG if p.unit_cost > p.selling_price * Decimal("0.9")]
    assert [p.sku for p in losers] == ["EARBUDS-PRO"]
def test_seed_catalog_currencies_are_valid(): ...
```

- [ ] **Step 2: Run, expect failure** — **Step 3: Implement `seed_data.py`** — **Step 4: Run, expect pass**

- [ ] **Step 5: Implement `seed_sandbox.py`**

Flow: `ensure_merchant`; upsert products and costs; for each product create `sales` orders. Strategy `card`: `payment_source = {"card": {"number": "4111111111111111", "expiry": "2030-12", "name": "Sandbox Buyer", "billing_address": {...US...}}}` with `intent=CAPTURE`; a COMPLETED order returns captures directly. Strategy `paypal`: create with `payment_source.paypal` and `experience_context.return_url`, print the approve links, then (if buyer credentials exist) run `approve_orders_playwright.py`, then `capture_order`. Strategy `links`: print approve links and wait for Enter, then capture. For each capture call `record_capture(source="seed")`. For `refunds` on a product, refund the last capture via `refund_capture(request_id=f"seed-{capture_id}")` and `record_refund(source="seed", reason="Seed: customer return")`. Print a per-currency summary: captures recorded, fee_known count, refunds recorded. Never print tokens or secrets.

- [ ] **Step 6: Run the seed for real**

Run: `python scripts/seed_sandbox.py --currency USD --strategy card`
Expected: output ends with `USD: captures=N fee_known=N refunds=1` with N at least 20. If the card strategy errors (print status and `debug_id` only), retry with `--strategy paypal`, then `--strategy links`. Then run `--currency EUR` if the EUR buyer exists; otherwise note "EUR skipped" in the report.

- [ ] **Step 7: Save three real responses as test fixtures**

Replace the hand-written `capture_completed.json` and `refund_completed.json` with sanitised real responses (remove emails and names). Re-run `pytest tests/integrations -q`, expect pass.

- [ ] **Step 8: Commit** `git commit -m "feat: sandbox seed script with card, paypal and link strategies"`

---

### Task 8: Event bus and SSE endpoint (Block 3)

**Files:**
- Create: `core/events.py`
- Modify: `main.py` (include router)
- Test: `tests/core/test_events.py`

**Interfaces:**
- Produces: `bus: EventBus` singleton with `publish(topic: str, payload: dict) -> None` (safe from any thread), `async subscribe(topics: set[str] | None = None) -> AsyncIterator[dict]`; topics `ledger.changed`, `task.changed`, `approval.changed`, `webhook.received`; router `GET /events?task_id=` streaming `event: <topic>\ndata: <json>\n\n` with a 15-second `: keepalive` comment.

- [ ] **Step 1: Write failing tests**

```python
async def test_subscriber_receives_published_payload(): ...
async def test_publish_from_thread_is_delivered(): ...   # publish via threading.Thread
def test_events_endpoint_streams_first_event(client): ... # read first chunk, assert "event: ledger.changed"
```

- [ ] **Step 2 to 4: Run (fail), implement, run (pass)**

- [ ] **Step 5: Commit** `git commit -m "feat: in-process event bus and SSE endpoint"`

---

### Task 9: Webhook endpoint with verification and dedupe (Block 3)

**Files:**
- Create: `domains/webhooks/__init__.py`, `models.py`, `schemas.py`, `service.py`, `router.py`
- Create: `migrations/versions/0003_webhook_events.py`
- Test: `tests/domains/webhooks/test_router.py`

**Interfaces:**
- Produces: model `WebhookEvent(id text pk = paypal event id, event_type, resource_type, resource_id, received_at, verified bool, processed_at nullable, error nullable, raw JSONB)`; `ingest(db, event: dict, *, verified: bool) -> bool` (True if newly stored); router `POST /webhooks/paypal` performing: raw body, verify (skip only in development with the flag), ingest, 200 `{"stored": bool}`, and `background_tasks.add_task(process_event, event_id)`; `process_event(event_id: str) -> None` opens its own session and dispatches to Task 10 handlers, sets `processed_at` or `error`, publishes `webhook.received`.

- [ ] **Step 1: Write failing tests**

```python
def test_invalid_signature_returns_400_and_stores_nothing(client, respx_mock): ...   # verify endpoint returns FAILURE
def test_valid_event_stored_once_and_duplicate_ignored(client, respx_mock): ...     # second post -> stored False, one row
def test_skip_verify_refused_outside_development(monkeypatch): ...
def test_raw_body_forwarded_unchanged(client, respx_mock): ...                        # verify request body contains original bytes
```

- [ ] **Step 2 to 4: Run (fail), implement, migrate, run (pass)**

- [ ] **Step 5: Commit** `git commit -m "feat: PayPal webhook endpoint with signature verification and dedupe"`

---

### Task 10: Webhook handlers (Block 3)

**Files:**
- Create: `domains/webhooks/handlers.py`
- Test: `tests/domains/webhooks/test_handlers.py`

**Interfaces:**
- Consumes: Task 6 ledger, Task 5 `parse_capture`/`parse_refund`, Task 8 bus. Task 19 later registers `on_refund_verified(db, refund: Refund, event_id: str)`; until then handlers call a `verification_hook` attribute defaulting to a no-op.
- Produces: `HANDLERS: dict[str, Callable[[Session, dict], None]]` keyed by event type; `handle(db, event: dict) -> None`.

- [ ] **Step 1: Write failing tests**

```python
def test_capture_completed_upserts_capture_with_fee(db): ...
def test_capture_refunded_before_capture_exists_creates_stub_then_links(db): ...  # Review Focus 1
def test_capture_reversed_sets_leakage(db): ...
def test_capture_denied_sets_status(db): ...
def test_order_approved_triggers_capture(db, respx_mock): ...   # capture_order called once
def test_unknown_event_type_is_ignored(db): ...
```

- [ ] **Step 2 to 4: Run (fail), implement, run (pass)**

- [ ] **Step 5: Commit** `git commit -m "feat: webhook handlers for capture, refund, reversal and order events"`

---

### Task 11: Webhook registration and first real verified event (Block 3)

**Files:**
- Create: `scripts/register_webhooks.py`
- Modify: `README.md` (local webhook section)

- [ ] **Step 1: Implement `register_webhooks.py`**

CLI `python scripts/register_webhooks.py --url https://<public>/webhooks/paypal` calling `ensure_webhook`; prints `webhook_id=<id>` and instructs to set `PAYPAL_WEBHOOK_ID`.

- [ ] **Step 2: Run end to end for real**

Run: `ngrok http 8000`, then the script with the ngrok URL, set `PAYPAL_WEBHOOK_ID` in `.env`, restart uvicorn. Issue a refund of a seeded capture through the adapter (`refund_capture(..., request_id="manual-1")`).
Expected within 90 seconds: server log `webhook stored id=WH-... type=PAYMENT.CAPTURE.REFUNDED verified=True`, then `SELECT id, event_type, verified, processed_at FROM webhook_event` shows one processed row and the refund row exists in `refund`. Replay the same event from the dashboard: log shows `duplicate ignored`.

- [ ] **Step 3: Commit** `git commit -m "feat: webhook registration script and local tunnel instructions"`

---

### Task 12: Finance calculator, per capture (Block 4)

**Files:**
- Create: `domains/finance/__init__.py`, `calculator.py`
- Test: `tests/domains/finance/test_calculator.py`

**Interfaces:**
- Produces: frozen dataclasses `CaptureLine(capture_id, product_id, currency, gross, paypal_fee: Decimal | None, refunded: Decimal, quantity: int, unit_cost: Decimal | None, variable_cost_per_unit: Decimal | None, captured_at)` and `MarginResult(gross, paypal_fee: Decimal | None, fee_known, refunded, net_proceeds, cogs: Decimal | None, variable: Decimal | None, contribution: Decimal | None, margin_pct: Decimal | None, cost_missing)`; `capture_margin(line: CaptureLine) -> MarginResult`. Rules: fee None treated as 0 with `fee_known=False`; cost None gives `cogs=None, contribution=None, margin_pct=None, cost_missing=True`; cogs counted even when refunded (documented); `margin_pct` is `contribution / gross` quantised to 4 places, None when gross is 0.

- [ ] **Step 1: Write failing tests** (spec values)

```python
def test_basic_margin(): line(gross="29.99", fee="1.54", refunded="0", qty=1, cost="27.50") -> contribution == Decimal("0.95")
def test_full_refund_counts_cogs(): refunded="29.99" -> contribution == Decimal("-29.04")
def test_partial_refund(): refunded="10.00" -> net_proceeds == Decimal("18.45")
def test_missing_fee_sets_fee_known_false(): ...
def test_missing_cost_sets_cost_missing_and_none_contribution(): ...
def test_zero_gross_gives_none_margin_pct(): ...
def test_quantity_multiplies_cogs_and_variable(): qty=3, cost="2.00", variable="0.50" -> cogs 6.00, variable 1.50
```

- [ ] **Step 2 to 4: Run (fail), implement, run (pass)** — **Step 5: Commit** `git commit -m "feat: deterministic per-capture margin calculator"`

---

### Task 13: Product aggregation, ranking, explanation (Block 4)

**Files:**
- Modify: `domains/finance/calculator.py`
- Test: `tests/domains/finance/test_aggregation.py`

**Interfaces:**
- Produces: `ProductSummary(product_id, currency, capture_count, gross, paypal_fee, refunded, net_proceeds, cogs: Decimal | None, contribution: Decimal | None, margin_pct: Decimal | None, cost_missing, fee_known_all, capture_ids: list[str])`; `product_summaries(lines: Sequence[CaptureLine]) -> list[ProductSummary]` (grouped by `(product_id, currency)`); `rank_products(lines, *, currency: str, limit: int, ascending: bool = True) -> list[ProductSummary]` (cost-missing products sorted last); `currency_totals(lines) -> list[CurrencyTotal(currency, capture_count, gross, paypal_fee, refunded, net_proceeds, contribution | None, margin_pct | None)]`; `explain_product(lines, product_id, currency) -> ProductExplanation(summary, fee_share_pct, refund_share_pct, cogs_share_pct, worst_captures: list[tuple[str, Decimal]])`.

- [ ] **Step 1: Write failing tests**

```python
def test_mixed_currencies_produce_two_totals_never_summed(): ...   # Review Focus 4
def test_rank_ascending_puts_loss_maker_first(): ...
def test_cost_missing_products_sorted_last(): ...
def test_explain_shares_sum_to_about_100_when_contribution_negative(): ...
```

- [ ] **Step 2 to 4** — **Step 5: Commit** `git commit -m "feat: product margin aggregation, ranking and explanation"`

---

### Task 14: Simulation and fee basis (Block 4)

**Files:**
- Modify: `domains/finance/calculator.py`
- Test: `tests/domains/finance/test_simulate.py`

**Interfaces:**
- Produces: `FeeBasis(rate: Decimal | None, sample_size: int, currency)`; `effective_fee_rate(lines, currency) -> FeeBasis` (sum fee / sum gross over `fee_known` lines); `SimulationResult(gross, est_paypal_fee: Decimal | None, est_net, cogs, variable, est_contribution, est_margin_pct: Decimal | None, fee_basis, fee_unknown: bool, estimated: bool = True)`; `simulate(*, currency, selling_price, alt_unit_cost, quantity: int = 1, fee_basis: FeeBasis, variable_cost_per_unit: Decimal | None = None) -> SimulationResult`.

- [ ] **Step 1: Write failing tests**

```python
def test_fee_basis_from_two_captures(): gross 29.99+29.99, fees 1.54+1.54 -> rate == Decimal("0.0514")
def test_fee_basis_zero_captures_is_none(): ...
def test_simulate_cost_lever(): price 29.99, alt cost 18.00, rate 0.0514 -> est_contribution == Decimal("10.45")
def test_simulate_price_lever(): price 34.99 ... -> est_margin_pct higher than at 29.99
def test_simulate_fee_unknown_reports_before_fees(): ...
```

- [ ] **Step 2 to 4** — **Step 5: Run coverage**

Run: `pytest tests/domains/finance --cov=marginos.domains.finance --cov-report=term-missing`
Expected: TOTAL at least 80%.

- [ ] **Step 6: Commit** `git commit -m "feat: margin simulation with observed fee basis"`

---

### Task 15: Finance service and router (Block 4)

**Files:**
- Create: `domains/finance/service.py`, `schemas.py`, `router.py`
- Modify: `main.py`
- Test: `tests/domains/finance/test_router.py`

**Interfaces:**
- Produces: `load_capture_lines(db, *, currency=None, product_id=None, date_from=None, date_to=None, limit=None) -> list[CaptureLine]`; `TransactionRow` schema (capture fields + `MarginResult` fields + `product_sku`, `product_title`, `status`, `leakage`, `verification: {source, ref} | None`); routes `GET /finance/transactions`, `GET /finance/summary`, `GET /finance/products?currency=&limit=&order=asc|desc`, `GET /finance/products/{product_id}/explain?currency=`, `POST /finance/simulate` (body per spec 3.3; `product_id` fills `selling_price` when omitted). All Decimals serialised as strings.

- [ ] **Step 1: Write failing tests** (seeded rows inserted by fixture)

```python
def test_transactions_returns_margin_fields_as_strings(client, db): ...
def test_summary_has_one_row_per_currency(client, db): ...
def test_simulate_uses_product_price_when_omitted(client, db): ...
def test_simulate_rejects_bad_currency(client): assert 422
```

- [ ] **Step 2 to 4** — **Step 5: Commit** `git commit -m "feat: finance API for transactions, summary, ranking and simulation"`

---

### Task 16: Catalog router (Block 5)

**Files:**
- Create: `domains/catalog/router.py`; Modify: `main.py`
- Test: `tests/domains/catalog/test_router.py`

**Interfaces:**
- Produces: `GET /products` (with current cost and per-currency summary fields from Task 13), `PATCH /products/{id}/cost {unit_cost, variable_cost_per_unit?}`, `PATCH /products/{id}/price {selling_price}`, `POST /products {sku, title, selling_price, currency, source, channel3_id?, unit_cost?}`; each write publishes `ledger.changed`.

- [ ] **Step 1: Tests**: `test_patch_cost_changes_transaction_margin(client, db)`, `test_patch_cost_rejects_negative(client)`, `test_post_product_from_channel3_sets_source(client)`.
- [ ] **Step 2 to 4** — **Step 5: Commit** `git commit -m "feat: catalog API with editable cost and price"`

---

### Task 17: Channel3 adapter, mapper, cache and discovery router (Block 5)

**Files:**
- Create: `integrations/channel3/__init__.py`, `client.py`, `mapper.py`; `domains/catalog/discovery.py`; route added to `domains/catalog/router.py`
- Test: `tests/integrations/channel3/test_mapper.py`, `tests/domains/catalog/test_discovery.py`

**Interfaces:**
- Produces: `Channel3Client(base_url, api_key, http=None)` with `search(query: str, *, max_price: Decimal | None, limit: int) -> list[dict]` (`POST /v1/search`, header `x-api-key`), `find_similar(product_id: str, *, limit) -> list[dict]`, `get_product(product_id) -> dict`; `Candidate(channel3_id, title, brand, description, image_url, retail_price: Decimal | None, currency: str | None, availability: str | None, url: str | None, key_features: list[str], fetched_at: datetime)`; `map_product(raw: dict, fetched_at) -> Candidate`; `search_alternatives(db, *, query: str | None, product_id: int | None, max_price=None, limit=10) -> DiscoveryResult(candidates, cached: bool, query_key)` caching in `Channel3Cache` for 24 hours; routes `POST /discovery/search {query?, product_id?, max_price?, limit?}`.

- [ ] **Step 1: Tests**: `test_map_product_reads_first_offer_price_and_main_image()`, `test_map_product_missing_price_is_none()`, `test_search_second_call_served_from_cache(db, respx_mock)` (one HTTP call), `test_search_error_returns_last_cached_when_available(db, respx_mock)`.
- [ ] **Step 2 to 4**
- [ ] **Step 5: Real call**: `python -c "...search('wireless earbuds', limit=3)..."` printing titles only. Expected: three titles. If 401: STOP, report the Channel3 key is missing.
- [ ] **Step 6: Commit** `git commit -m "feat: Channel3 discovery adapter with cache"`

---

### Task 18: Approvals, tasks, audit models and state machine (Block 6)

**Files:**
- Create: `domains/approvals/__init__.py`, `models.py`, `schemas.py`, `service.py`
- Create: `migrations/versions/0004_approvals.py`
- Test: `tests/domains/approvals/test_service.py`

**Interfaces:**
- Produces: models per spec 3.7 (`Task`, `TaskStep`, `Approval`, `AuditEvent`); constants `TASK_STATES`, `ALLOWED_TRANSITIONS: dict[str, set[str]]` (`planned -> {awaiting_approval, executing, verified, failed}`, `awaiting_approval -> {executing, rejected, failed}`, `executing -> {awaiting_verification, failed}`, `awaiting_verification -> {verified, failed}`); service `create_task(db, title, origin_message_id=None) -> Task`, `transition(db, task, to: str, *, actor: str, detail: dict) -> Task` (raises `IllegalTransition`), `add_step(db, task, *, tool, input) -> TaskStep`, `finish_step(db, step, *, output, status)`, `create_approval(db, task, *, kind, payload, preview, evidence, requested_by) -> Approval` (moves task to `awaiting_approval`), `reject(db, approval_id, actor) -> Approval`, `audit(db, *, kind, actor, detail, task_id=None, approval_id=None) -> AuditEvent`, `mark_verified(db, task, *, source: str, ref: str) -> Task`.

- [ ] **Step 1: Tests**: `test_illegal_transition_raises()`, `test_every_transition_writes_audit_event()`, `test_create_approval_moves_task_to_awaiting_approval()`, `test_reject_sets_both_statuses()`, `test_mark_verified_records_source_and_ref()`.
- [ ] **Step 2 to 4** (migrate) — **Step 5: Commit** `git commit -m "feat: tasks, approvals and audit with enforced state machine"`

---

### Task 19: Approval execution, idempotency, verification, poll fallback (Block 6)

**Files:**
- Create: `domains/operations/executor.py`, `domains/operations/verification.py`, `domains/approvals/router.py`, `core/ratelimit.py`
- Modify: `domains/webhooks/handlers.py` (set `verification_hook = verification.on_refund_event`), `main.py`
- Test: `tests/domains/approvals/test_execution.py`, `tests/domains/approvals/test_router.py`

**Interfaces:**
- Produces: `approve(db, approval_id: int, *, actor: str) -> Approval` in `approvals/service.py` (locks the row `FOR UPDATE`; if already `executed` returns it unchanged; else sets `executing`, calls `executor.execute(db, approval)`, stores `api_response`, `external_id`, moves task to `awaiting_verification`; on `PayPalError` stores the body and moves task to `failed`); `executor.execute(db, approval) -> dict` dispatching on `approval.kind` (`refund` now; `invoice` P1) with `request_id=str(approval.id)`; `verification.on_refund_event(db, refund: Refund, event_id: str)` marks the matching task verified with `source="webhook"`; `verification.poll_refund(task_id: int, refund_id: str, *, deadline_s=90, interval_s=10)` background function marking `source="api_poll"` or leaving the task in `awaiting_verification` with an audit note; routes `GET /approvals?status=`, `POST /approvals/{id}/approve` (rate limited 10/min/IP), `POST /approvals/{id}/reject`, `GET /tasks`, `GET /tasks/{id}` (task, steps, approvals, audit events, webhook events by `verification_ref`), `GET /audit/events`, `GET /audit/webhooks`, `GET /audit/health` (`last_event_at, verified_count, duplicates_ignored, failed_verifications`).

- [ ] **Step 1: Tests**

```python
def test_approve_twice_executes_one_refund(db, respx_mock): ...                  # Review Focus 2: one outbound POST
def test_refund_over_remaining_amount_marks_task_failed_not_500(client, db, respx_mock): ...  # Review Focus 3: 422 body stored
def test_webhook_refund_event_verifies_task(db): ...
def test_poll_fallback_verifies_with_api_poll_source(db, respx_mock, monkeypatch): ...
def test_approve_rate_limited_after_10(client): ...
def test_task_detail_includes_webhook_event_by_ref(client, db): ...
```

- [ ] **Step 2 to 4** — **Step 5: Commit** `git commit -m "feat: approval execution with idempotency, webhook and poll verification"`

---

### Task 20: Checkpoint A, real refund through the approval path (Block 6)

**Files:**
- Create: `scripts/checkpoint_a.py`

- [ ] **Step 1: Implement the script**

Creates a task "Checkpoint A", an approval of kind `refund` for the most recent un-refunded seeded USD capture with amount `5.00`, calls `POST /approvals/{id}/approve` over HTTP against the running server, then polls `GET /tasks/{id}` every 5 seconds for up to 120 seconds printing `status` and `verification_source`.

- [ ] **Step 2: Run with ngrok and webhooks registered**

Expected final line: `status=verified source=webhook ref=WH-...` (or `source=api_poll` if the webhook is late; both pass, but note which). Paste the output into the block report.

- [ ] **Step 3: Commit** `git commit -m "test: checkpoint A script for approval-gated refund verification"`

---

### Task 21: LLM client adapter with fallback (Block 7)

**Files:**
- Create: `integrations/llm/__init__.py`, `client.py`, `providers.py`
- Test: `tests/integrations/llm/test_client.py`

**Interfaces:**
- Produces: `PROVIDERS = {"openai": ("https://api.openai.com/v1", "openai_api_key", "openai_model"), "groq": ("https://api.groq.com/openai/v1", ...), "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", ...)}`; `ToolCall(id, name, arguments: dict)`; `ChatResponse(content: str | None, tool_calls: list[ToolCall], provider: str)`; `LLMClient.chat(messages: list[dict], tools: list[dict]) -> ChatResponse` trying primary, one retry on 429/5xx, then fallback; `get_llm_client()`.

- [ ] **Step 1: Tests**: `test_primary_500_falls_back_to_secondary(respx_mock)`, `test_tool_calls_parsed_with_json_arguments(respx_mock)`, `test_missing_key_for_provider_raises_config_error()`.
- [ ] **Step 2 to 4**
- [ ] **Step 5: Real call**: one chat with no tools, print `provider` and the first 40 characters. If auth fails: STOP and ask for a key.
- [ ] **Step 6: Commit** `git commit -m "feat: OpenAI-compatible LLM client with provider fallback"`

---

### Task 22: Orchestrator tools (Block 7)

**Files:**
- Create: `orchestrator/__init__.py`, `tools/__init__.py`, `tools/registry.py`, `tools/finance_tools.py`, `tools/discovery_tools.py`, `tools/operations_tools.py`, `tools/report_tools.py`
- Test: `tests/orchestrator/test_tools.py`

**Interfaces:**
- Produces: `ToolSpec(name, description, params: type[BaseModel], handler: Callable[[Session, Task, BaseModel], dict])`; `REGISTRY: dict[str, ToolSpec]`; `openai_tool_defs() -> list[dict]`; the nine tools named exactly as spec 3.6 with Pydantic param models; every handler returns JSON-serialisable dicts with Decimals as strings and an `evidence: list[str]` of IDs; `request_refund` returns `{"approval_id", "status": "pending", "preview"}` and creates nothing else.

- [ ] **Step 1: Tests**: `test_rank_products_tool_returns_evidence_ids(db)`, `test_request_refund_creates_approval_and_no_refund_row(db)`, `test_request_refund_resolves_order_id_to_capture(db)`, `test_simulate_tool_rejects_unknown_currency(db)`, `test_tool_defs_are_valid_json_schema()`.
- [ ] **Step 2 to 4** — **Step 5: Commit** `git commit -m "feat: typed orchestrator tools over domain services"`

---

### Task 23: Orchestrator runner, post-check, chat router (Block 7)

**Files:**
- Create: `orchestrator/models.py` (`ChatMessage`), `orchestrator/prompts/system.md`, `orchestrator/postcheck.py`, `orchestrator/runner.py`, `orchestrator/router.py`
- Create: `migrations/versions/0005_chat.py`
- Test: `tests/orchestrator/test_postcheck.py`, `tests/orchestrator/test_runner.py`

**Interfaces:**
- Produces: `find_unsupported_amounts(reply: str, tool_outputs: list[dict]) -> list[str]` (tokens matching `\d[\d,]*\.\d{2}` in the reply not present in any stringified tool output); `run_turn(task_id: int, user_message: str) -> None` (loop up to 8 tool calls; each call becomes a `TaskStep`; publishes `task.changed` events `{"kind": "plan"|"tool_call"|"tool_result"|"message"|"approval"|"report"}`; on an unsupported amount, appends a system correction and retries once, then replaces the reply with the tool-backed report); routes `POST /chat {message, task_id?} -> {task_id}` (runs `run_turn` in background), `GET /chat/messages?task_id=`.
- System prompt content fixed by spec 3.6 (cite IDs, label sample and sandbox data, label Channel3 prices as retail discovery, never claim completion unless a tool result says verified, never do arithmetic, use `get_task_report` for the final report).

- [ ] **Step 1: Tests**

```python
def test_postcheck_flags_amount_not_in_tool_outputs(): assert find_unsupported_amounts("You lost 42.00", [{"x": "29.99"}]) == ["42.00"]   # Review Focus 5
def test_postcheck_allows_amounts_from_outputs(): ...
def test_runner_records_steps_and_stops_at_8_calls(db, fake_llm): ...
def test_runner_side_effect_tool_leaves_task_awaiting_approval(db, fake_llm): ...
```

- [ ] **Step 2 to 4** (migrate) — **Step 5: Commit** `git commit -m "feat: orchestrator runner with evidence post-check and chat API"`

---

### Task 24: Demo prompt dry runs (Block 7)

**Files:**
- Create: `scripts/demo_prompts.py`

- [ ] **Step 1: Implement**

Sends the three demo prompts in sequence against the running server (`POST /chat`), waits for each task to leave `planned`/`executing`, prints the tool names called and the final message, and asserts: prompt 1 called `rank_products_by_margin`; prompt 2 called `search_alternatives` and `simulate_margin`; prompt 3 called `request_refund` and the task is `awaiting_approval`. Exit code 1 on any miss.

- [ ] **Step 2: Run three times**

Run: `for i in 1 2 3; do python scripts/demo_prompts.py || break; done`
Expected: three `ALL PROMPTS OK` lines with the provider name. Paste the tool-call lists into the block report.

- [ ] **Step 3: Commit** `git commit -m "test: scripted demo prompt dry run"`

---

## Block report format (after every block)

```
Block N: <name>
Completed: <features>
Tests: <command> -> <passed/failed counts>
Real calls: <what was called, status, IDs; no secrets>
Outstanding: <issues>
Next: <block>
```
