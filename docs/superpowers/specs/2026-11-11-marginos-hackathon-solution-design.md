# MarginOS — Hackathon Solution Design (revision 2, post critical review)

Date: 2026-11-11
Status: Awaiting owner approval. No application code has been written.
Target: PayPal "Build What's Next with PayPal and AI" hackathon. Submission closes 12 Nov 2026
12:00 pm PST (13 Nov 2026, 1:30 am IST). Confirm the hour on the Devpost page.

This revision replaces revision 1 in full. It records a critical review against the judging
criteria, the weaknesses found, the corrections adopted, and the final scope, UX, plan, demo
script and acceptance criteria. Where this document and `CLAUDE.md` or the PRD disagree, this
document wins; the disagreements are listed in section 2.5.

Nothing in this document has been tested against PayPal, Channel3 or an LLM yet. Every
integration claim below is from vendor documentation and is marked with the build block in which
it gets verified.

---

## 0. Security: mandatory first step

### 0.1 What is exposed

`apps/env.example` is committed (commit `e3d1736`) with a real PayPal sandbox client ID and
secret and a real Channel3 API key. The remote `arjunhareeshs/MoriginOS` on GitHub is public and
in sync with local `main`. Treat both credentials as compromised. They are not reproduced here
and must not be pasted anywhere again.

### 0.2 Rotation (owner, about 10 minutes)

1. PayPal: Developer Dashboard, Apps & Credentials, Sandbox tab, open the app. Under Secret key,
   choose Generate new secret. Copy the new secret into the local `.env` only. Then delete the
   old secret. The client ID may stay (it is public by design) but a fresh app is cleaner if the
   dashboard allows it in two minutes.
2. Channel3: dashboard, API keys, revoke the exposed key, create a new one, copy into `.env`.
3. Confirm the old secret is dead: a token request with the old pair must return 401. Do this
   with a throwaway shell variable, never by writing the old value into a file.

### 0.3 Repository cleanup (builder, about 15 minutes, after rotation)

1. Replace every value in `apps/env.example` with placeholders (`PAYPAL_CLIENT_ID=`,
   `PAYPAL_CLIENT_SECRET=`, `CHANNEL3_API_KEY=`). Add `.gitignore` with `.env`, `.env.*`,
   `!.env.example`, `*.local`, `node_modules/`, `.venv/`, `dist/`, `__pycache__/`.
2. Commit: `chore: remove credentials from env example, add gitignore`.
3. Rewrite history so the secret is not in the public log (optional once rotated, but judges
   read repos). The repository owner runs, on a fresh clone:

   ```
   pip install git-filter-repo
   git filter-repo --path apps/env.example --invert-paths
   git add apps/env.example   # re-add the clean version
   git commit -m "chore: add clean env example"
   git remote add origin https://github.com/arjunhareeshs/MoriginOS.git
   git push --force origin main
   ```

   Every collaborator then re-clones. Do this before anyone else pushes, or skip it and rely on
   rotation. GitHub may keep cached commit views; GitHub Support can purge them, but rotation
   already makes the leak harmless.
4. Verify: `git log --all -p -- apps/env.example | grep -c "PAYPAL_CLIENT_SECRET="` shows only
   placeholder lines, and `git grep -n "x-api-key\|CHANNEL3_API_KEY" -- ':!*.md'` shows only
   placeholders.
5. Going forward: secrets live in local `.env` and Render environment variables only. The API
   refuses to start if a required secret is missing; it never logs secret values.

### 0.4 Other owner actions needed before Block 2

- Provide one working LLM API key (OpenAI preferred for tool-calling reliability; Groq or
  Gemini work through the same adapter) and its model name.
- Confirm two sandbox buyer accounts exist: one US (USD) and one EUR. Put their logins in
  `.env` as `PAYPAL_BUYER_US_EMAIL/PASSWORD` and `PAYPAL_BUYER_EU_EMAIL/PASSWORD` (used by the
  seed script only; never deployed).
- Note whether the sandbox app shows "Advanced credit and debit card payments" enabled.

Repo hygiene done in Block 0: `README.md` is UTF-16 and renders as garbage on GitHub; rewrite it
as UTF-8. Leave `hello.md` and the placeholder READMEs in place (owner asked for no deletions).

---

## 1. Critical judging-criteria assessment of revision 1

Scores are my estimate of how a judge would rate the revision-1 design if built exactly as
written, on a 1 to 5 scale, followed by what changes in this revision.

| Criterion | Rev 1 | Why | Change adopted in rev 2 |
|---|---|---|---|
| Technological implementation | 4 | Orders, Payments, Webhooks with postback verification, idempotency, Channel3, typed tools. Only one write operation (refund) is demonstrated, and no live capture is shown. | Add a second PayPal write as P1 (invoice create and send). Make webhook-backed capture events visible in the Overview activity feed so judges see live PayPal lifecycle events, not only a refund. |
| Design | 3 | Six screens with no stated relationships; the Workspace was "chat plus evidence panel", which reads as a chatbot. | Workspace becomes the hub: every request is a Task with a visible plan, evidence chips, embedded grids, inline approvals and a structured report. Every other screen deep-links into it with context. Design tokens and states specified per screen. |
| Potential impact | 4 | Clear persona and pain. Numbers were not on screen. Channel3 framing ("find a cheaper product") invites the question "why would a merchant source from a retail listing?" | The demo shows a concrete loss figure per product. Channel3 is framed honestly as market discovery and selling-price benchmark; the merchant supplies cost. |
| Innovation | 4 | Evidence to approval to execution to verification is the differentiator. It was described, not made visible. | Verification source (webhook or API poll, with event ID) is a first-class column and chip everywhere. The improvement plan includes deterministic price what-ifs, so the AI proposes and the maths proves. |
| Presentation | 3 | Script relied on a webhook arriving on cue and had no "how it works" beat. | Script re-timed with fallback, a five-second architecture frame, and three dry runs required before recording. |

## 2. Weaknesses found and corrections

### 2.1 Missing capabilities that would cost points

| Gap | Cost | Correction | Priority |
|---|---|---|---|
| Only one PayPal write operation shown | Tech | Invoice create plus send through the same approval gate | P1 |
| AI improvement plan had no deterministic lever other than "swap product" | Innovation, impact | `simulate_margin` accepts `alt_selling_price` and `alt_unit_cost`; the report shows "raise price to X restores margin to Y%" with the calculation | P0 |
| No way to see the AI's work from other screens | Design | "Ask MarginOS about this" row action on Transactions and Products opens the Workspace with the entity pinned | P0 |
| Report not shareable | Presentation | Report block has "Copy as Markdown" and a permalink `/tasks/{id}` | P1 |
| Webhook health not visible | Tech credibility | Audit screen header shows last event time, verified count, duplicates ignored | P0 (cheap) |
| Command palette for the "OS" feel | Design | `Ctrl/Cmd+K` palette: ask, jump to screen, open a capture by ID | P2 |

### 2.2 Unnecessary complexity removed

- `Transaction` as a materialised table: replaced by a finance query that joins captures,
  refunds and costs at read time. One fewer migration and no staleness bug.
- `ChatThread` multi-thread UI: one thread per merchant for the demo; the table stays, the UI
  shows one conversation.
- `TaskStep` as a separate table: kept, because the task timeline is the proof view, but it is
  written only by the orchestrator runner, never by handlers.
- Reconcile job against Transaction Search: P2.
- Separate SSE library: plain `StreamingResponse`; the frontend hook falls back to 3-second
  polling if the stream drops, so SSE is never a demo risk.

### 2.3 Technical assumptions that could fail in the demo, with the mitigation

| Assumption | Failure mode | Mitigation | Verified in |
|---|---|---|---|
| Sandbox orders with `payment_source.card` capture without buyer approval | App lacks card processing; API returns an error | Seed falls back to PayPal-funded orders approved by Playwright; final fallback is the owner clicking the printed approve links for 10 orders (about 10 minutes) | Block 2 |
| Capture response includes `seller_receivable_breakdown.paypal_fee` | Fee missing for some payment sources or pending captures | Ledger stores `fee_known=false`; grid shows "fee pending"; margin shows as "before fees" for that row | Block 2 |
| `PAYMENT.CAPTURE.REFUNDED` resource ID equals the refund ID returned by the refund call | Task cannot be matched | Match on refund ID first, then on the capture ID from the resource `links` entry with `rel=up`; store both at execution time | Block 3 |
| Webhook delivery within 90 seconds | Task stuck in awaiting verification on camera | API poll of `GET /v2/payments/refunds/{id}` every 10 seconds; task becomes "Verified via API poll"; both paths are honest and visible | Block 6 |
| ngrok URL stable during local demo | Free ngrok URL changes on restart, webhook registration goes stale | `register_webhooks.py` is idempotent (PATCH if a webhook for our app exists); run it after each ngrok restart; use a reserved ngrok domain if the account has one | Block 3 |
| Postback verification works with the raw body | Re-serialised JSON fails verification | Endpoint reads `await request.body()` and forwards the bytes unchanged | Block 3 |
| Channel3 returns results for the demo query | Empty results or rate limit on camera | Search results are cached in Postgres per normalised query for 24 hours; the demo query is run during the dry runs so it is warm | Block 5 |
| LLM tool calling behaves | Model skips tools or invents numbers | System prompt forbids arithmetic; tool results are the only numbers; a post-check rejects an assistant message that contains a currency amount not present in any tool result for that turn and asks the model to retry once; fallback provider on error | Block 7 |
| EUR captures work for the sandbox merchant | Currency not enabled | Seed USD first; EUR is additive; the UI is per-currency by construction | Block 2 |

### 2.4 Impressive on paper, hard to demonstrate (cut or downgraded)

- Live buyer checkout in the video: shows Orders v2 end to end but needs a buyer login on
  camera. P2. The seeded captures plus webhook-backed activity feed already prove the capture
  path.
- Customer intelligence, Reports builder, Integrations screen, Elastic: not built. The Devpost
  text describes what exists, not the PRD.
- Multi-agent anything: one orchestrator with typed tools, as the PRD itself recommends.

### 2.5 Contradictions between PRD, CLAUDE.md and this design, resolved

| Source says | This design does | Why |
|---|---|---|
| PRD P0 "PayPal sandbox OAuth; merchant connects account" | Client-credentials for one sandbox merchant from env; header shows "Connected: sandbox merchant, Sandbox" | Third-party access needs partner status; the PRD's own section 17 accepts sandbox constraints |
| PRD P0 "real sandbox order/capture" | Done by the seed script and visible as webhook-backed activity, not performed live in the video | Live checkout is a demo-reliability risk (section 2.4) |
| PRD lists 13 application sections | Six screens | Time; the six cover the full demo path |
| CLAUDE.md "deploy last" | Deploy in Block 11 of 13, before recording | Webhooks need the production URL registered and tested before the video |
| CLAUDE.md "Elastic optional and last" | Not built | Time |
| PRD "Redis for cache/coordination, worker queue" | Neither; FastAPI background tasks and in-process pub/sub | One service to deploy and debug |

## 3. Final architecture

### 3.1 Shape

One FastAPI service, one Vite static site, one Postgres on Render. No Redis, no worker.

```
Browser (React 19, TypeScript, Tailwind, AG Grid Community 34)
   |  REST (JSON)  +  GET /events (SSE, 3s-poll fallback)
   v
FastAPI (apps/api)
   orchestrator/  LLM loop + typed tools  ->  domains/  services  ->  integrations/
                                              catalog, finance,       paypal/ (httpx)
                                              operations, approvals,  channel3/ (httpx)
                                              webhooks                llm/ (OpenAI-compatible)
   POST /webhooks/paypal : raw body -> postback verify -> dedupe -> 200 -> background process
   PostgreSQL via SQLAlchemy 2 + Alembic
```

Architecture rules from `CLAUDE.md` stand unchanged: only `integrations/` talks to the
outside; the LLM only calls `orchestrator/tools/`; money-moving tools create approvals; finance
is pure `Decimal` and never imports the LLM; nothing is "done" until the API or a webhook says
so; every consequential action writes an `AuditEvent`; secrets are server-side only; sandbox and
sample data are labelled.

### 3.2 Money: the app's own ledger

Captures are recorded from the capture API response at seed time and from
`PAYMENT.CAPTURE.COMPLETED` webhooks. Refunds are recorded from the refund API response and from
`PAYMENT.CAPTURE.REFUNDED`. Transaction Search is not on the critical path.

Product linkage: every order sets `purchase_units[0].custom_id` to the product SKU and
`items[]` with SKU, quantity and unit price. Capture responses and webhooks carry `custom_id`
back, so out-of-order webhooks can still map to a product. Unknown SKUs are stored with
`product_id = null` and shown as "Unmapped", never dropped.

### 3.3 Margin maths (`domains/finance`, pure, `Decimal`, per currency)

```
gross        = capture.amount
paypal_fee   = capture.seller_receivable_breakdown.paypal_fee      (fee_known=false if absent)
refunded     = sum(refund.amount for refunds on the capture)
net_proceeds = gross - paypal_fee - refunded
cogs         = unit_cost * quantity                                 (ProductCost, "Sample data")
variable     = variable_cost_per_unit * quantity                    (optional)
contribution = net_proceeds - cogs - variable
margin_pct   = contribution / gross                                 (null when gross = 0)
```

Per product: sums per currency only; ranking by margin % within a currency; currencies reported
separately. Missing cost returns `cost_missing: true`, never zero.

Simulation (`POST /finance/simulate` and the `simulate_margin` tool):

```
input : { currency, selling_price, alt_unit_cost, quantity=1,
          product_id?, alt_selling_price?, variable_cost_per_unit? }
output: { gross, est_paypal_fee, est_net, cogs, est_contribution, est_margin_pct,
          fee_basis: { rate, sample_size, currency }, estimated: true }
```

The fee estimate is the merchant's observed effective fee rate for that currency over the ledger
(fees divided by gross). `fee_basis` lets the UI say "fee estimated from N captures". With no
captures in that currency: `fee_unknown: true` and the UI shows margin before fees, labelled.

### 3.4 Webhooks (verification backbone)

`POST /webhooks/paypal`:

1. Read raw bytes. Verify by posting `transmission_id`, `transmission_time`, `cert_url`,
   `auth_algo`, `transmission_sig`, `webhook_id` and the raw event to
   `/v1/notifications/verify-webhook-signature`. Reject unless `verification_status == SUCCESS`.
   `PAYPAL_WEBHOOK_SKIP_VERIFY=true` is honoured only when `APP_ENV=development` and logs a
   warning on every request; the production settings validator refuses it.
2. Insert `WebhookEvent` keyed by PayPal event ID. On conflict, return 200 and stop.
3. Return 200; process in a background task. Handlers are idempotent upserts that tolerate
   missing parents (stub rows with `source="webhook"`).
4. Event handling: `PAYMENT.CAPTURE.COMPLETED` upserts the capture and recalculates the product
   snapshot; `PAYMENT.CAPTURE.REFUNDED` upserts the refund, matches the task by refund ID or
   capture ID, marks it `verified` with `verification_source="webhook"` and the event ID;
   `DENIED` and `PENDING` set capture status and raise an Overview alert; `REVERSED` flags
   leakage; `CHECKOUT.ORDER.APPROVED` captures the order; `INVOICING.INVOICE.PAID`,
   `CANCELLED`, `REFUNDED` update the invoice (P1).
5. Publish `ledger.changed` or `task.changed` on an in-process pub/sub; `GET /events` streams
   them; grids flash changed cells.

Verification fallback: after execution a task enters `awaiting_verification` with a 90-second
window; a background poll checks the refund (or invoice) status every 10 seconds; on
`COMPLETED` the task becomes `verified` with `verification_source="api_poll"`. The UI always
shows which source verified it.

`scripts/register_webhooks.py` creates or patches the webhook for the current public URL with
the event list above and prints the webhook ID.

### 3.5 Approval gate, tasks, audit

- Side-effect tools (`request_refund`, `request_invoice`) never execute. They create
  `Approval(pending)` with a human-readable preview and the evidence used, and return
  `{approval_id, status: "pending"}` to the model.
- `POST /approvals/{id}/approve` is the only execution path. It sends
  `PayPal-Request-Id = approval.id`, stores the raw response and the external ID, writes an
  `AuditEvent`, and moves the task to `awaiting_verification`. Reject moves it to `rejected`.
- Task states: `planned`, `awaiting_approval`, `executing`, `awaiting_verification`,
  `verified`, `failed`, `rejected`. Every transition is an `AuditEvent`. The LLM cannot change
  state.
- Approve is rate limited to 10 per minute per IP. The hosted demo has no login (single sandbox
  merchant); the README says so and that approvals move sandbox money only. CORS allows
  `WEB_BASE_URL` only.

### 3.6 Orchestrator

One loop, max 8 tool calls per turn, OpenAI-compatible chat completions with function calling.
Adapter in `integrations/llm/client.py` takes `base_url`, `api_key`, `model`; primary and
fallback providers from env; one retry on 429 or 5xx then fallback.

| Tool | Does |
|---|---|
| `list_transactions(currency?, product_id?, date_from?, date_to?, limit)` | ledger rows with margin fields and IDs |
| `rank_products_by_margin(currency, limit, order="asc")` | ranking with per-product evidence capture IDs |
| `explain_product_margin(product_id, currency)` | per-capture breakdown: fee share, refund share, cost share |
| `search_alternatives(query?, product_id?, max_price?, limit)` | Channel3 search or find-similar, cached |
| `simulate_margin(...)` | section 3.3 contract |
| `get_capture(capture_id)` | PayPal capture detail |
| `request_refund(capture_id? , paypal_order_id?, amount?, currency, reason)` | resolves order to capture, defaults to full refund, creates approval |
| `request_invoice(customer_email, items[], currency)` (P1) | creates approval for create plus send |
| `get_task_report(task_id?)` | completed, pending, failed with evidence |

Every turn creates or continues a `Task`. The runner writes a `TaskStep` per tool call and
streams `plan`, `tool_call`, `tool_result`, `message`, `approval`, `report` events. The system
prompt: cite capture or order IDs for every financial claim; label sample costs and sandbox
data; label Channel3 prices as retail discovery data; never claim completion unless a tool
result says `verified`; never perform arithmetic. A post-check rejects a reply containing a
money amount that does not appear in that turn's tool results and asks for one retry.

### 3.7 Data model

```
Merchant(id, name, paypal_email, currency_default)
Product(id, sku, title, description, image_url, selling_price, currency, source, channel3_id?, created_at)
ProductCost(id, product_id, unit_cost, variable_cost_per_unit, currency, label="Sample data", effective_from)
Order(id, paypal_order_id, status, currency, buyer_email, custom_id, created_at, raw)
Capture(id, paypal_capture_id, order_id?, product_id?, quantity, gross, paypal_fee, fee_known, net, currency, status, captured_at, source, raw)
Refund(id, paypal_refund_id, capture_id, amount, currency, status, reason, created_at, source, raw)
Invoice(id, paypal_invoice_id, status, total, currency, customer_email, raw)                    # P1
Task(id, title, origin_message_id, status, verification_source?, verified_at?, verification_ref?, report(json))
TaskStep(id, task_id, seq, tool, input(json), output(json), status, started_at, finished_at)
Approval(id, task_id, kind, payload(json), preview, evidence(json), status, requested_by, decided_by?, decided_at?, idempotency_key, api_response(json)?, external_id?)
AuditEvent(id, task_id?, approval_id?, actor, kind, detail(json), created_at)                   # append-only
WebhookEvent(id = paypal_event_id, event_type, resource_type, resource_id, received_at, verified, processed_at?, error?, raw)
Channel3Cache(query_key, fetched_at, results(json))
ChatMessage(id, task_id?, role, content, tool_calls(json), created_at)
```

Money: `Numeric(18,2)` plus `currency CHAR(3)`. Timestamps: `timestamptz` UTC.

### 3.8 Hosting

`render.yaml`: web service for `apps/api` (uvicorn, `alembic upgrade head` on release), static
site for `apps/web`, Postgres free tier. Secrets set in the Render dashboard. After deploy:
register the production webhook, run the refund path once, then record.

## 4. Final prioritised scope

### P0 (the video does not work without these)

1. Secrets rotated and scrubbed; MIT LICENSE; UTF-8 README with 5-command local run.
2. PayPal adapter: token cache, create order, capture, get capture, refund, verify webhook
   signature, create or patch webhook. Seed script producing 20 or more USD captures (EUR if the
   buyer exists).
3. Webhook endpoint with verification, dedupe, background processing, refund and capture
   handlers, SSE publish.
4. Finance service with tests at 80% or more coverage: per-capture margin, product ranking,
   explain, simulate with price and cost levers.
5. Catalog with sample costs; editable cost and price persisted.
6. Channel3 adapter: search and find-similar, mapped to a product candidate, cached.
7. Approvals, tasks, audit with the full state machine and both verification sources.
8. Orchestrator with the nine tools (invoice tool excluded), streaming, the three demo prompts
   passing three consecutive dry runs.
9. Screens: Overview, Workspace, Transactions, Products, Approvals and Tasks, Audit, as specified
   in section 5, with loading, empty and error states, responsive at 390 and 1440.
10. Render deploy with production webhook; demo path passes on the hosted URL.
11. Video, Devpost text, repository instructions.

### P1 (add only after P0 passes on the hosted URL)

1. Invoice create and send through the approval gate, with `INVOICING.INVOICE.*` webhooks.
2. Report permalink and "Copy as Markdown".
3. Catalog price change as an approval-gated internal action, so the improvement plan can be
   executed, not only proposed.
4. CSV export on the Transactions grid (AG Grid Community `exportDataAsCsv`).

### P2 (only if time remains, in this order)

1. Command palette.
2. Transaction Search reconciliation job marking ledger rows reconciled.
3. Live buyer checkout clip.
4. Dispute webhooks surfaced as alerts.

## 5. Final six-screen UX specification

### 5.1 Shared frame and design direction

Direction: "a ledger, not a dashboard". Dense, calm, high contrast, one accent colour reserved
for primary actions and verified states, a warning colour for pending or failed, tabular
numerals everywhere money appears. Font pairing and exact tokens are written in
`apps/web/DESIGN.md` before any UI code (builder's call, with the reason stated there). Spacing on
a 4-px scale; radii small; no gradients, glass or glow; motion limited to cell flash and chip
transitions, disabled under `prefers-reduced-motion`.

Frame: a 240-px left rail with the six destinations and a pending-approvals badge; a top bar
with the merchant name, a "Sandbox" badge, the connected PayPal sandbox email, and an "Ask
MarginOS" input that opens the Workspace with the typed text. The current screen's title and a
per-currency switcher (All, USD, EUR) sit under the top bar; "All" never sums currencies, it
shows them side by side.

Shared components: `MoneyCell` (Intl formatting, currency from the row), `StatusChip` (task and
capture states), `VerificationChip` (Verified via webhook, Verified via API poll, Awaiting
verification, Not verified, with event or refund ID on hover), `EvidenceChip` (capture, order,
refund or product ID; click opens the detail drawer), `ApprovalCard` (used in Workspace and
Approvals identically), `GridShell` (AG Grid with theme bound to tokens, quick filter, column
state, loading overlay, empty overlay, error banner).

AG Grid Community capabilities used, and only these: column groups, sorting, filtering, quick
filter, editable cells with `onCellValueChanged`, `valueFormatter`, cell flashing,
`pinnedBottomRowData`, tooltips, CSV export (P1). No row grouping, status bar or master-detail
(Enterprise).

### 5.2 Overview

Purpose: the morning brief. Answers "what happened, what is wrong, what needs me".

Layout at 1440: a per-currency summary strip across the top (one row per currency: gross, PayPal
fees, refunds, net proceeds, contribution, margin %, capture count), then two columns. Left,
"Needs attention": ranked rows with a reason and an action ("Investigate" opens the Workspace
with the product pinned; "Review" opens the approval). Right, "Activity": a live feed built from
webhook events and audit events with verification chips and relative times.

States: empty ledger shows "Run the seed script" with the command; loading skeleton rows; SSE
loss shows "Reconnecting" and polls.

### 5.3 Workspace (the operating hub)

Purpose: where the merchant runs the business. Not a chat window: a task runner with a
conversation as its control surface.

Layout at 1440, three regions:

- Left, 280 px: "Start an investigation" with four suggested prompts (the three demo prompts
  and "What needs my attention today?"), and the list of recent tasks with status chips.
- Centre: the conversation. Each merchant message starts a Task card. The assistant's turn
  renders as: a plan (numbered steps, each with tool name, elapsed time and a status dot that
  streams in), evidence chips, an embedded grid when the result is tabular (ranking table,
  alternatives table, both real AG Grid instances with the same column definitions as the full
  screens), an `ApprovalCard` when an approval was created, and a Report block at the end
  (Findings, Evidence, Proposed actions, Status). Prose is short; numbers appear in tables.
- Right, 320 px: Context rail. Pinned entities (product, captures), the active task's state
  machine as a vertical stepper, pending approvals for this task, and "Open in Transactions"
  or "Open in Products" links.

Interactions: clicking an evidence chip opens the detail drawer over the Workspace. Typing
"Approve" in chat does nothing; approval happens only through the card button, and the
assistant says so. When a webhook verifies the task, the stepper advances, the chip turns
accent, and a toast says "Verified by PayPal webhook, event <id>".

At 390: the rails collapse into tabs (Tasks, Conversation, Context).

### 5.4 Transactions

Purpose: the ledger. Every row is a PayPal capture.

Grid columns in groups: Payment (date, order ID, capture ID, product, qty, gross, PayPal fee,
refunds, net), Costs (unit cost, variable, "Sample data" marker), Margin (contribution, margin %),
Status (capture status, verification). Per-currency pinned bottom totals. Quick filter, column
filters, sort by margin % ascending as the default. Row actions: "Explain margin" and "Refund"
open the Workspace with the capture pinned and the prompt prefilled; the merchant still sends
it. Rows with `fee_known=false` show "fee pending" and a muted margin.

Detail drawer: capture summary, refunds list, related task and approval, audit events, and a
Raw tab showing the stored PayPal JSON.

Cells flash on SSE updates (refund arrives, status changes).

### 5.5 Products

Purpose: catalog economics and discovery.

Top: the catalog grid (SKU, title, selling price, unit cost editable, variable cost editable,
captures, gross, contribution, margin % per currency, "Sample data" marker). Editing cost or
price saves and recalculates the row through the backend; the row flashes.

Row action "Find alternatives" opens the comparison panel below (split view). Search bar at the
top of the panel is prefilled with the product title and category; the merchant can retype.
Results render in the comparison grid: a pinned-top row for the current product, then
candidates: image, title, brand, retail price (labelled "Retail listing, Channel3, fetched at
<time>"), availability, acquisition cost (editable, empty by default with a "needed" marker),
selling price (editable, defaults to the current product's price), est. fee (tooltip: fee basis),
est. net, est. contribution, est. margin %, and a delta column versus the current product.
Editing acquisition cost or selling price calls `POST /finance/simulate` and updates the row.
Row actions: "Save to catalog" (creates a Product with `source="channel3"` and the entered cost),
"Use in plan" (pins it in the Workspace context).

Empty results show "No listings matched; try a broader query". Channel3 errors show a banner and
keep the last cached results if any.

### 5.6 Approvals and Tasks

Purpose: control. Everything that moves money waits here.

Top: pending approvals as `ApprovalCard`s: kind, amount and currency, target (capture or order
ID), reason, evidence (gross, fee, net before and after), requested by, and Approve or Reject
with a confirm step that repeats the amount. After approval the card shows the PayPal response
summary and the verification chip updating live.

Below: the tasks grid (title, created, status, verification, approvals count, last event).
Clicking a task opens the task timeline: plan steps with inputs and outputs, approval decision,
API call with request ID and response status, webhook event with ID and time, verification
source. This timeline is the proof view and is what the video lingers on.

### 5.7 Audit

Purpose: the record. Cheap to build and high in credibility.

Header line: webhook health (last event received at, events verified, duplicates ignored,
failed verifications). Two grids with a tab switch: Audit events (time, actor, kind, task,
approval, detail) and Webhook events (time, type, resource ID, verified, processed, error).
Filters by task and type. Row click opens the raw JSON.

### 5.8 Screen relationships

Overview points to Workspace (Investigate) and Approvals (Review). Transactions and Products
point to Workspace (Explain, Refund, Find alternatives, Use in plan). Workspace points to
Approvals (approval card link), Transactions and Products (context rail links) and Audit (the
"proof" link on a verified task). Approvals points to Audit (task timeline "View raw events").
Every ID anywhere is an `EvidenceChip` that opens the same drawer.

## 6. Revised hour-by-hour implementation plan (30 hours)

Vertical slice first: the refund path must work end to end through the API by hour 14 and in
the browser by hour 24. Stop-loss checkpoints are marked.

| Hours | Block | Deliverable | Verification (must be shown, not claimed) |
|---|---|---|---|
| 0.0 to 0.5 | 0 | Rotation confirmed by owner; scrub env example; `.gitignore`; LICENSE; UTF-8 README stub | Old credentials return 401; `git grep` shows placeholders only |
| 0.5 to 2.5 | 1 | API scaffold: FastAPI, pydantic-settings, SQLAlchemy 2, Alembic, Docker Postgres, `money.py`, pytest, ruff | `alembic upgrade head`; `GET /health` 200; `pytest` runs |
| 2.5 to 5.5 | 2 | PayPal adapter (token cache, orders, capture, get capture, refund, verify, webhooks mgmt) with respx tests; seed script; **run the seed** | 20+ captures in DB with fee values; one manual refund via adapter returns COMPLETED |
| 5.5 to 7.5 | 3 | Webhook endpoint, verification, dedupe, handlers, in-process pub/sub, `GET /events`; ngrok; `register_webhooks.py` | A real sandbox refund produces a stored, verified `WebhookEvent` and updates the ledger; a replayed event is ignored (log shown) |
| 7.5 to 9.5 | 4 | Finance domain by TDD: per-capture, per-product, ranking, explain, simulate | `pytest --cov=marginos.domains.finance` at 80% or more |
| 9.5 to 11.0 | 5 | Catalog and costs API; transactions API; Channel3 adapter, mapper, cache | `curl` for each endpoint; one Channel3 search stored in cache |
| 11.0 to 14.0 | 6 | Approvals, tasks, audit services and routers; approve executes; poll fallback | Integration test with respx; one real run: approve, refund, webhook (or poll) verifies. **Checkpoint A: API demo path works via curl** |
| 14.0 to 17.0 | 7 | LLM adapter, tools, prompt, runner, streaming, post-check | Script runs the three prompts; each shows the expected tool calls; three consecutive clean runs |
| 17.0 to 18.0 | 8 | Web scaffold: Vite, Tailwind tokens from `DESIGN.md`, router, API client, SSE hook with poll fallback, `GridShell`, shared components | `tsc --noEmit` and `npm run build` clean |
| 18.0 to 20.5 | 9 | Transactions grid, detail drawer, Overview | Playwright screenshots at 390 and 1440; cell flash on a real refund |
| 20.5 to 23.0 | 10 | Products catalog grid, Channel3 search, comparison grid with simulate | Edit a cost, margin updates; screenshots |
| 23.0 to 25.0 | 11 | Workspace (task cards, embedded grids, approval card, report, context rail), Approvals and Tasks, Audit | Full demo path in the browser recorded as dry run 1. **Checkpoint B: browser demo path works** |
| 25.0 to 26.5 | 12 | Polish pass: states, focus, contrast, copy, `web-design-guidelines` review; dry runs 2 and 3 | Screenshots re-shot; issues list closed |
| 26.5 to 28.0 | 13 | Render deploy, production webhook, README final, demo script, hosted dry run | Demo path passes on the hosted URL |
| 28.0 to 30.0 | 14 | Record, edit, upload video; Devpost text; submit | Submitted at least 3 hours before close |

If Checkpoint A slips past hour 16: drop EUR, drop `explain_product_margin` (ranking already
carries evidence), keep going. If Checkpoint B slips past hour 26: fold Audit into the task
timeline, simplify Overview to the activity feed, record locally over ngrok instead of on
Render, and still submit the Render URL once it is up.

P1 items are attempted only after Block 13 passes, in the order listed in section 4.

## 7. Final three-minute demonstration script

Recorded at 1440 wide after three clean dry runs, with the LLM warm and ngrok or Render webhook
delivery tested within the previous ten minutes. Narration is spoken; on-screen text is minimal.

| Time | Screen and action | Narration |
|---|---|---|
| 0:00 to 0:15 | Overview. Per-currency strip; "Needs attention" shows a product with a negative contribution. | "Revenue is not profit. This merchant sells through PayPal in two currencies. Sales look fine. One product is losing money after fees, refunds and cost. MarginOS is the operating system that finds that, fixes it through PayPal, and proves it." |
| 0:15 to 0:35 | Transactions. Sort by margin %. Hover a fee cell. Open the drawer on a capture, show the Raw tab briefly. | "Every row is a real PayPal sandbox capture: gross, PayPal's fee, refunds, net, the merchant's cost, contribution. Nothing is typed in by hand or made up by a model." |
| 0:35 to 1:05 | Workspace. Send "Which products have the lowest margin and why?" Plan streams; embedded ranking grid; evidence chips; report block. Click a chip to open the drawer. | "The AI plans, calls deterministic finance tools, and cites capture IDs. It never does the arithmetic. Here is the worst product, and here is why: fees and a refund wiped the margin." |
| 1:05 to 1:40 | Send "Find alternatives for the worst one and tell me what would fix the margin." Products comparison grid appears inline; type an acquisition cost; margins recalculate; report shows the price what-if. | "Channel3 finds comparable products and the market price. The merchant enters their supplier cost, and the margin recalculates through the backend. The plan shows two levers: a substitute product, or a price change, with the maths." |
| 1:40 to 2:05 | Send "Refund the most recent order of that product, the customer complained." Approval card appears. Click Approve, confirm the amount. | "Money only moves after the merchant approves. The request is idempotent and audited." |
| 2:05 to 2:35 | Task stepper advances; webhook arrives; chip turns "Verified via PayPal webhook" with the event ID; Transactions cell flashes; open the task timeline. | "PayPal executes the refund. Its webhook comes back, signature verified, and only then does MarginOS mark the task verified. The full trail: plan, approval, API call, webhook." |
| 2:35 to 2:50 | Report block: completed, pending, failed. Audit header shows webhook health. | "One report: what was done, what is pending, what failed, with evidence." |
| 2:50 to 3:00 | Architecture frame (one slide): PayPal, Channel3, finance engine, approval gate, webhooks. | "PayPal is the financial truth. Channel3 is discovery. Deterministic maths in the middle. The AI connects them. MarginOS." |

If the webhook has not arrived by 2:20 in a take, continue: the API poll verifies within ten
seconds and the narration becomes "and if the webhook is late, MarginOS confirms through the
API and says so". Both outcomes are acceptable takes.

## 8. Acceptance criteria for every P0 feature

Each criterion is checked by running the stated command or action and observing the stated
result. "Done" is claimed only with that output in hand.

1. Security and repo
   - Old credentials rejected by the PayPal token endpoint (401) and Channel3 (401 or 403).
   - `apps/env.example` contains placeholders only; `.gitignore` excludes `.env`.
   - `LICENSE` (MIT) at the root; README is UTF-8 and includes the run commands.

2. PayPal adapter and seed
   - `pytest apps/api/tests/integrations/test_paypal.py` passes against recorded responses.
   - `python scripts/seed_sandbox.py --count 20` ends with "20 captures recorded" and
     `SELECT count(*) FROM capture WHERE fee_known` returns at least 20.
   - A refund issued through the adapter returns `status: COMPLETED` and is stored.

3. Webhooks
   - A real sandbox refund produces a `WebhookEvent` with `verified = true` within 90 seconds
     (log line shown).
   - Posting the same event twice results in one row and a second log line "duplicate ignored".
   - An event with a tampered signature returns 400 and is not stored.
   - After a `PAYMENT.CAPTURE.REFUNDED` event, the related task is `verified` with
     `verification_source = webhook` and `verification_ref` equal to the event ID.

4. Finance
   - `pytest --cov=marginos.domains.finance` reports 80% or more.
   - Tests cover: full refund, partial refund, missing fee, missing cost, zero quantity, two
     currencies never summed, ranking order, simulate with cost lever, simulate with price
     lever, fee basis with zero captures.

5. Catalog and Channel3
   - `PATCH /products/{id}/cost` persists and the transactions endpoint reflects the new margin.
   - `POST /discovery/search` returns at least one candidate for the demo query and a second
     identical call is served from cache (`cached: true`).

6. Approvals, tasks, audit
   - A `request_refund` tool call creates an approval and executes nothing (no refund row).
   - `POST /approvals/{id}/approve` executes once; a second call returns the same result without
     a second PayPal call (same `PayPal-Request-Id`, log shows one outbound request).
   - With webhooks disabled, the task reaches `verified` via `api_poll` within 100 seconds.
   - Every state transition has an `AuditEvent` row.

7. Orchestrator
   - The three demo prompts each produce the expected tool calls (ranking, search plus simulate,
     request_refund) in three consecutive runs, logged.
   - A reply containing a money amount absent from tool results is rejected by the post-check
     (unit test with a fabricated reply).
   - Provider failure (simulated 500) falls back to the second provider.

8. Screens
   - `tsc --noEmit` and `npm run build` pass.
   - Playwright screenshots at 390 and 1440 exist for all six screens, with no horizontal
     scroll at 390.
   - Transactions: editing nothing, sorting by margin % puts the seeded loss-making product first;
     per-currency pinned totals match the API totals.
   - Products: entering an acquisition cost changes est. margin % within one second and the
     request to `/finance/simulate` is visible in the network log.
   - Workspace: the three prompts render plan, embedded grid, approval card and report; approving
     from the inline card updates the stepper without reload.
   - Approvals and Tasks: the task timeline shows plan, approval, API call and webhook rows.
   - Audit: webhook health header shows a non-zero verified count after the demo path.
   - Keyboard: every action reachable by Tab and Enter; focus visible; contrast AA on text.

9. Deploy
   - Hosted URL loads the Overview with seeded data; production webhook registered; the refund
     path verified once on production with the task showing `webhook` as the source.

10. Submission
   - Video under 3 minutes on YouTube, public; Devpost text lists PayPal APIs (Orders v2,
     Payments v2, Webhooks), Channel3, AG Grid, Render and the LLM provider used; repo public
     with LICENSE visible in About.

## 9. What is left to the builder

- Font pairing, accent colour and token values (in `DESIGN.md`, with reasons).
- Which LLM key is available on the day; the adapter must not care.
- Whether sandbox card payments work for this app (try first; fall back fast).
- respx versus JSON fixtures for recorded PayPal responses.
- Exact ngrok invocation and whether a reserved domain is available.
