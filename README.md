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
- Field-agent engine (`agent_engine.py`) computes all-in unit costs, expected margin/ROI, candidate scores and fail-closed order/loss-limit decisions using decimal money arithmetic.
- `POST /agent/analyze` ranks up to 100 user-supplied candidates; it does not fetch live market data.
- Owner-protected `POST /agent/worker/run-once` processes one queued task in analysis-only mode; profitability tasks can rank supplied candidate records, while unsupported live tasks fail closed.
- Verified-profit alert formatter rejects notifications unless settlement and cost reconciliation are confirmed.
- Integration readiness registry (`integration_registry.py`) reports missing credentials but deliberately never enables live transactions.
- Provider adapter contracts (`provider_adapters.py`) validate USD amounts, report integration readiness and fail closed for checkout, webhook verification and marketplace purchases until official provider-specific adapters are approved and implemented.
- Read-only Amazon SP-API catalog search connector (`amazon_catalog.py`), exposed through owner-protected `POST /agent/research/amazon-catalog`; it requires approved developer/seller credentials and explicit opt-in, and does not place orders.
- Container deployment guide, non-root Docker image, healthcheck, `.dockerignore`, and persistent-volume Compose setup.
- `GET /api/v1/integrations` includes provider readiness details without revealing secret values.
- Purchase proposal workflow with idempotency keys, approval-required state and per-action cap.
- Background task queue foundation with a narrow allowlist of non-financial task types.
- Responsive dashboard served at `/ui`.
- OpenAPI docs at `/docs`, tests and GitHub Actions workflow. See [container deployment](docs/DEPLOYMENT.md).

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

No production-ready live payment adapter or Amazon ordering/AliExpress/Alibaba/shipping API client is connected in this release. Amazon catalog lookup is read-only and requires approved SP-API credentials. Provider adapter contracts are intentionally fail-closed and do not simulate successful payment or purchase results. Environment variables are placeholders/status indicators only. Credentials alone do not establish country eligibility or API approval. Do not enable any `*_LIVE_ENABLED` flag until the provider-specific adapter, signed webhook validation, idempotent reconciliation, sandbox tests and compliance review are complete.

Before implementation, verify business and country eligibility directly with the chosen provider. A real adapter must validate signed server-to-server webhooks, payment amount/currency, merchant identity, cycle ownership, duplicate event IDs, refunds and disputes before confirming ledger entries. Browser redirects must never credit balances. See [the integration go-live checklist](docs/INTEGRATIONS_AND_GO_LIVE.md) and the [Field Agent architecture](docs/FIELD_AGENT_ARCHITECTURE.md).

Amazon integration requires approved official SP-API access and seller authorization. Supplier API availability depends on the official platform/program. Do not scrape, bypass verification, or misrepresent location or identity.

## Agent autonomy and safety

The worker can process queued profitability-analysis tasks when the payload contains complete candidate data. It does not autonomously fetch market data or execute financial operations. For local testing, start the app with secure environment variables and call `POST /agent/worker/run-once` with `X-Admin-Key`; one task is processed per call. Current branch adds a deterministic opportunity engine and a field-agent architecture guide. The queue still stores tasks; it does not yet run an autonomous marketplace worker. Next stages are verified data connectors, durable worker execution, monitoring/alerts, sandbox testing, and tightly scoped execution permissions. Purchases, ads, refunds, listings, contracts, and external commitments require explicit authorization until their controls are proven.

## Tests

```bash
pytest -q
```

GitHub Actions runs the test suite on pushes to `main` and pull requests. Check the Actions tab for the actual run result.

## Deployment warning

Do not expose this SQLite-based MVP publicly as a financial production service. Before public deployment, migrate to managed PostgreSQL, add HTTPS, rate limits, email verification, MFA, password reset, secret management, database backups, security monitoring, provider webhook verification and independent legal/compliance review. Never store raw card data.


## RedotPay Connect sandbox (new)

A sandbox-only, owner-protected endpoint is available at `POST /agent/funding/redotpay/sandbox-checkout`. It creates a hosted checkout order for a user and returns it as `pending_payment`; it never credits the user's ledger. Configure `REDOTPAY_ENV=sandbox`, `REDOTPAY_APP_KEY`, `REDOTPAY_PRIVATE_KEY_PATH`, and `REDOTPAY_KEY_VERSION` using provider-issued sandbox credentials. The endpoint requires `X-Admin-Key` and is not a public end-user funding API.

**Important:** RedotPay Connect checkout is a merchant payment-collection flow. It does not give the agent spending access to a user's card and does not authorize Amazon purchases. Live RedotPay mode is intentionally blocked in this release. Real sandbox E2E validation requires your own RedotPay sandbox credentials and a test callback; unit tests are not a claim of provider acceptance. See [RedotPay sandbox guide](docs/REDOTPAY_SANDBOX.md).

Example request (local sandbox only):

```bash
curl -X POST http://127.0.0.1:8000/agent/funding/redotpay/sandbox-checkout \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -d '{"user_id":"demo-user","order_id":"VZX123456","amount_usd":10.00}'
```

A returned checkout URL is only a pending payment session. Do not add funds to a user's available balance until signed callback verification, final provider reconciliation, exact user/order/amount/currency matching, and idempotency have been implemented and reviewed.
