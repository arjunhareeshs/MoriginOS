# MarginOS

MarginOS is an AI commerce operating system for merchants, built for the PayPal AI Hackathon
2026. It connects product discovery (Channel3), profit intelligence (deterministic margin maths on
PayPal captures, fees and refunds plus merchant-supplied costs) and approval-gated PayPal
operations (refunds, invoices) in one workspace, with every action verified by PayPal webhooks.

**Status:** hackathon build in progress. Design: `docs/superpowers/specs/`. Plan:
`docs/superpowers/plans/`.

## Local run

Prerequisites: Python 3.13, Node 23, Docker.

```bash
cp apps/env.example .env            # then fill in the values
docker compose up -d db             # Postgres 16 on localhost:5433 (5432 is often taken)
cd apps/api && pip install -e ".[dev]"
alembic upgrade head
uvicorn marginos.main:app --reload --port 8000
```

Tests:

```bash
cd apps/api && pytest
```

## Security notes

- The hosted demo is a single-tenant PayPal **sandbox** deployment. Approving an action moves
  sandbox money only.
- Secrets live in the repo-root `.env` (gitignored) and in Render environment variables.
  `apps/env.example` contains placeholders only.
- Webhook signatures are verified with PayPal's postback endpoint. Verification cannot be
  disabled in production.

## License

MIT, see `LICENSE`.
