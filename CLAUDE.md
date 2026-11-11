# MarginOS — build brief for Claude Code

MarginOS is an AI commerce operating system for merchants, built for the PayPal AI Hackathon 2026.
It connects product discovery (Channel3), profit intelligence (deterministic margin maths on PayPal
data plus merchant-supplied costs) and approved PayPal operations (refunds, invoices, orders) in one
workspace. Full product definition lives in the two project docs:
`MarginOS_Problem_and_Solution_Document.docx` and `MarginOS_Product_Requirements_Document.docx`.

## Deadline and submission rules

- Submission closes 12 Nov 2026. Sources disagree on the hour (12:00 pm PST vs 2:00 pm PT); plan for
  12:00 pm PST = 1:30 am IST on 13 Nov, and confirm on https://paypalaihackathon.devpost.com/.
- Required: working hosted demo, public GitHub repo with an open-source LICENSE file at the root,
  public YouTube demo video under 3 minutes, text description.
- Judged equally on: Technological Implementation, Design, Potential Impact, Innovation, Presentation.
- Judges may score from the video alone, so the demo path below must work end to end.
- Demo must stay live and free to access until 15 Dec 2026.

## Stack

- Backend: Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL. Redis only if a worker is needed.
- Frontend: React, TypeScript, Vite, Tailwind CSS, AG Grid Community.
- AI: one central orchestrator with typed tools (not multiple autonomous agents). LLM provider: TBD.
- Hosting: Render (API web service, static site, Postgres). Deploy happens LAST, after the app
  works locally. Do not start with a hello-world deploy.

## Repository layout (domain-oriented monorepo)

```
marginos/
├── apps/
│   ├── api/
│   │   ├── src/marginos/
│   │   │   ├── main.py
│   │   │   ├── core/               # config, db, security, logging, money.py
│   │   │   ├── integrations/
│   │   │   │   ├── paypal/         # client.py, orders.py, payments.py, invoicing.py,
│   │   │   │   │                   # reporting.py, webhooks.py
│   │   │   │   ├── channel3/       # client.py, mapper.py
│   │   │   │   └── llm/
│   │   │   ├── domains/
│   │   │   │   ├── catalog/        # products, costs, alternatives
│   │   │   │   ├── finance/        # margin calculator, reconciliation
│   │   │   │   ├── operations/     # refunds, invoices, orders
│   │   │   │   ├── approvals/      # approval gate + audit log
│   │   │   │   └── webhooks/       # receive, verify, dedupe, dispatch
│   │   │   ├── orchestrator/       # agent.py, tools/, prompts/
│   │   │   └── workers/
│   │   ├── migrations/
│   │   ├── tests/
│   │   └── pyproject.toml
│   └── web/
│       └── src/
│           ├── app/                # routes, providers, layout
│           ├── features/           # chat/, products/, transactions/, approvals/, tasks/
│           ├── components/         # shared UI, grid/ (AG Grid wrappers)
│           └── lib/                # api client, money + date formatters
├── scripts/                        # seed_sandbox.py, register_webhooks.py
├── docs/                           # architecture.md, demo-script.md
├── render.yaml
├── .env.example
├── LICENSE                         # MIT
└── README.md
```

Each domain folder holds `router.py`, `service.py`, `models.py`, `schemas.py`.

## Architecture rules (do not break these)

1. Only code in `integrations/` talks to external APIs. Domains call adapters, never raw HTTP.
2. The LLM only calls tools in `orchestrator/tools/`. Tools call domain services.
3. Any tool that moves money or sends something (refund, invoice send, order capture) must create
   an Approval record and wait for the merchant to approve in the UI before executing.
4. `domains/finance/` is pure deterministic code using `Decimal`. It never imports the LLM. The LLM
   never calculates or invents financial values.
5. Never report an action as completed until the API response or a webhook confirms it.
6. Every consequential action writes an AuditEvent (who, what, approval, API result, verification).
7. Secrets stay server-side in environment variables. Nothing sensitive reaches the browser.
8. Sandbox data is labelled "Sandbox"; merchant costs used for the demo are labelled "Sample data".

## Global by design

- Every amount is `Decimal` + ISO 4217 currency code. Never sum across currencies; group by
  currency or convert with an explicitly labelled rate.
- Store timestamps in UTC; display in the user's timezone.
- Format money and dates in the frontend with `Intl.NumberFormat` / `Intl.DateTimeFormat`.
- No hard-coded country logic (no INR, GST or country tax rules). Tax and fees are line items
  from source data.
- UI strings in one place so translation is possible later. English only for now.
- PayPal sandbox business and buyer accounts should be US accounts; add a EUR buyer to show
  multi-currency.

## Integrations

### PayPal (sandbox base URL: https://api-m.sandbox.paypal.com)

- Auth: client-credentials token from `/v1/oauth2/token` using the sandbox app's client ID and
  secret; cache until expiry. Use the app's own sandbox merchant (third-party Transaction Search
  access needs PayPal partner status, so no multi-merchant OAuth for the MVP).
- Orders v2: create order, buyer approves in browser, capture.
- Payments v2: capture details (gross, PayPal fee, net), full/partial refunds. Send a
  `PayPal-Request-Id` idempotency key on every write.
- Invoicing v2: create draft, send, remind, cancel.
- Transaction Search (`/v1/reporting/transactions`): max 31-day window per query, paginated, and
  new transactions can take up to 3 hours to appear. Seed sandbox data early; use direct
  order/capture lookups and webhooks for anything created live.
- Consider the official `paypal-agent-toolkit` Python package for ready-made tools, wrapped with
  our approval gate.

### PayPal webhooks

Endpoint: `POST /webhooks/paypal`.
Flow: read raw body → verify via `POST /v1/notifications/verify-webhook-signature` (headers
`PAYPAL-TRANSMISSION-ID`, `PAYPAL-TRANSMISSION-TIME`, `PAYPAL-CERT-URL`, `PAYPAL-AUTH-ALGO`,
`PAYPAL-TRANSMISSION-SIG`, plus our webhook ID and the event body) → store in `WebhookEvent`
keyed by event ID, ignore duplicates → return 200 quickly → process: update records and mark the
matching task verified. Handle out-of-order events. Simulator mock events cannot be verified by
postback, so test with real sandbox events.

Subscribe to:
- `CHECKOUT.ORDER.APPROVED` — capture the order
- `PAYMENT.CAPTURE.COMPLETED` — record capture, fee, net; recalculate margin
- `PAYMENT.CAPTURE.DENIED`, `PAYMENT.CAPTURE.PENDING` — surface failed/pending state
- `PAYMENT.CAPTURE.REFUNDED` — verified outcome for the refund flow
- `PAYMENT.CAPTURE.REVERSED` — flag as profit leakage
- `INVOICING.INVOICE.PAID`, `INVOICING.INVOICE.CANCELLED`, `INVOICING.INVOICE.REFUNDED`
- `CUSTOMER.DISPUTE.CREATED`, `CUSTOMER.DISPUTE.RESOLVED` (optional)

Local development needs a public tunnel URL for webhooks until the Render deploy exists.

### Channel3 (https://api.trychannel3.com, docs: https://docs.trychannel3.com)

- Auth: `x-api-key` header, or the `channel3_sdk` Python package.
- `POST /v1/search` for free-text search with price/availability filters;
  `GET /v1/products/{id}` for detail; find-similar by product ID for alternatives.
- Listings are retail discovery data, not wholesale quotes. Show provider and timestamp; the
  merchant supplies acquisition cost.

### AG Grid

- Transactions grid: gross, fee, refunds, net, cost, contribution margin, currency, source ID.
- Product comparison grid: Channel3 alternatives side by side with an editable cost column that
  recalculates margin through the backend.

### Elastic

Optional and last. Postgres search is enough for the demo.

### Render

`render.yaml` blueprint: API web service, static site for the frontend, Postgres. Done at the end.

## Environment variables (.env.example)

```
PAYPAL_ENV=sandbox
PAYPAL_CLIENT_ID=
PAYPAL_CLIENT_SECRET=
PAYPAL_WEBHOOK_ID=
CHANNEL3_API_KEY=
LLM_API_KEY=
DATABASE_URL=
APP_BASE_URL=
```

## The one demo path that must work

1. Workspace shows seeded sandbox transactions in the grid with fee, net and margin.
2. Merchant asks: "Which products have the lowest margin and why?" → orchestrator calls finance
   tools → evidence-backed answer with source transaction IDs.
3. "Find alternatives for the worst one" → Channel3 results in the comparison grid → merchant
   enters a cost → margin recalculates.
4. "Refund order X" (or "invoice customer Y") → approval card → merchant approves → PayPal call →
   webhook arrives → task shows Verified with the audit trail.
5. Final consolidated report: completed, pending, failed.

## Build order

1. Scaffold the repo, LICENSE, `.env.example`, local Postgres.
2. PayPal adapter + `scripts/seed_sandbox.py`; run the seed immediately (3-hour reporting delay).
3. Webhook endpoint with verification and dedupe.
4. Catalog + costs, margin calculator with tests, transactions grid.
5. Channel3 adapter and comparison grid.
6. Orchestrator, tools, approval UI, verified-task state.
7. README with run instructions, demo script.
8. Deploy to Render, register the production webhook URL, record the video, submit early.

Cut order if time runs short: Elastic, invoices, separate worker (use FastAPI background tasks).
