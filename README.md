# Autonomous Commerce OS

A multi-user commerce-operations control plane with isolated accounts, declared budgets, a per-user ledger, product opportunity scoring, purchase proposals, and a durable task-queue foundation.

> **Important status:** This is an early-stage application, not a fully autonomous live ecommerce company. Authentication and per-user budget records are implemented, but payment collection, money transfers, Amazon orders/listings, supplier purchases, shipping, and unattended external actions are **disabled**. Do not collect other people's money or promise returns with this MVP.

## Implemented

- Per-user registration/login with PBKDF2 password hashing and signed, expiring bearer tokens.
- Per-user budget cycles, ledger history, proposal records and basic audit events.
- Declared budgets remain `pending_payment`; they are not counted as available cash.
- Default loss-stop policy of 30% of the declared cycle capital.
- 80% reinvestment policy documented for future accounting integration; not yet automatically applied to verified profits.
- Product opportunity scoring based on demand, competition, margin, supplier reliability, fulfilment fit and compliance risk.
- Purchase proposal workflow with idempotency keys, approval-required state and per-action cap.
- Background task queue foundation with a narrow allowlist of non-financial task types.
- Responsive dashboard served at `/ui`.
- OpenAPI docs at `/docs`, tests and GitHub Actions workflow.

## Run locally

Python 3.12 recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Generate secrets:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Put one generated value in `AUTH_SECRET` and a separate generated value in `ADMIN_API_KEY` in `.env`. Keep `.env` private and never commit it.

```bash
uvicorn app:app --host 127.0.0.1 --port 8000
```

Open:
- Dashboard: http://127.0.0.1:8000/ui
- API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## Multi-user API

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/me`
- `GET /api/v1/account`
- `POST /api/v1/budget`
- `GET /api/v1/ledger`
- `POST /api/v1/proposals`
- `GET /api/v1/proposals`
- `POST /api/v1/tasks`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/integrations`

Private endpoints require `Authorization: Bearer <token>`. Never share access tokens. This MVP does not yet provide email verification, password reset, MFA, or public-production abuse protection.

## Payment and marketplace status

No live payment adapter or Amazon/AliExpress/Alibaba/shipping API client is connected in this release. Environment variables are placeholders/status indicators only. Credentials alone do not establish country eligibility or API approval.

Before implementation, verify business and country eligibility directly with the chosen provider. A real adapter must validate signed server-to-server webhooks, payment amount/currency, merchant identity, cycle ownership, duplicate event IDs, refunds and disputes before confirming ledger entries. Browser redirects must never credit balances. See [the integration go-live checklist](docs/INTEGRATIONS_AND_GO_LIVE.md).

Amazon integration requires approved official SP-API access and seller authorization. Supplier API availability depends on the official platform/program. Do not scrape, bypass verification, or misrepresent location or identity.

## Agent autonomy and safety

The task queue currently stores allowed requests; it does not autonomously fetch market data or execute financial operations. Next implementation stages are: verified data connectors, durable worker execution, monitoring/alerts, sandbox testing, and tightly scoped execution permissions. Purchases, ads, refunds, listings, contracts, and external commitments require explicit authorization until their controls are proven.

## Tests

```bash
pytest -q
```

GitHub Actions runs the test suite on pushes to `main` and pull requests. Check the Actions tab for the actual run result.

## Deployment warning

Do not expose this SQLite-based MVP publicly as a financial production service. Before public deployment, migrate to managed PostgreSQL, add HTTPS, rate limits, email verification, MFA, password reset, secret management, database backups, security monitoring, provider webhook verification and independent legal/compliance review. Never store raw card data.
