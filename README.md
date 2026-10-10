# VZX-Tool

**VZX-Tool** is a risk-controlled commerce research and operations prototype for evaluating resale opportunities, tracking user-scoped tasks, and preparing provider integrations without pretending that simulated funds are real money.

> **Current release: research + simulation.** Live customer-fund custody, card spending, marketplace purchasing, Amazon listings, and automatic reinvestment are not enabled. RedotPay Connect is implemented as a sandbox hosted-checkout request only. Do not use this repository as a production financial service.

## Capabilities

- FastAPI control plane with an HTML dashboard.
- Account/session APIs, scoped task queue, proposals, audit records, and budget-cycle primitives.
- Deterministic resale opportunity scoring from candidate data supplied to the API.
- Owner-protected Amazon SP-API catalog research (read-only, requires approved Amazon credentials and explicit opt-in).
- RedotPay Connect Open API v2 sandbox checkout creation with RSA request signing.
- Automated tests, Docker image build, and container health smoke test in GitHub Actions.
- Safe defaults: no live payment or marketplace execution; owner-only operations fail closed if `ADMIN_API_KEY` is missing.

## Repository

- Application: `app.py`
- Account/task API: `platform_api.py`
- Opportunity engine: `agent_engine.py`
- Analysis-only worker and queue: `agent_worker.py`
- RedotPay sandbox checkout: `redotpay_connect.py`
- Amazon read-only catalog connector: `amazon_catalog.py`
- Provider readiness contracts: `provider_adapters.py`
- Deployment guide: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
- RedotPay sandbox guide: [`docs/REDOTPAY_SANDBOX.md`](docs/REDOTPAY_SANDBOX.md)
- Integration go-live gates: [`docs/INTEGRATIONS_AND_GO_LIVE.md`](docs/INTEGRATIONS_AND_GO_LIVE.md)
- Execution contract: [`docs/EXECUTION_CONTRACT.md`](docs/EXECUTION_CONTRACT.md)

## Quick start (local / simulation)

Requires Python 3.12+.

```bash
git clone https://github.com/nagatoara4/VZX-Tool.git
cd VZX-Tool
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Generate unique local secrets and place them in `.env` (never commit that file):

```bash
python -c "import secrets; print('ADMIN_API_KEY=' + secrets.token_urlsafe(48)); print('AUTH_SECRET=' + secrets.token_urlsafe(48))"
```

Set `ADMIN_API_KEY` and `AUTH_SECRET` in `.env`, then start:

```bash
uvicorn app:app --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Keep the service bound to localhost while testing. Never expose it publicly without the production checklist in `docs/DEPLOYMENT.md`.

## Docker

```bash
cp .env.example .env
# Edit .env and set strong unique ADMIN_API_KEY and AUTH_SECRET values.
docker compose up --build
```

Compose binds to `127.0.0.1:8000` by default and persists app data in a named volume. Review the compose file and secret handling before deploying on any server.

## Automated validation

GitHub Actions runs:

1. dependency installation,
2. `pytest -q`,
3. Docker image build,
4. container startup and `/health` smoke test.

See [the latest Actions runs](https://github.com/nagatoara4/VZX-Tool/actions). A passing CI run validates code tests and the container smoke test; it does **not** prove that RedotPay or Amazon credentials are approved or that a provider-backed sandbox transaction succeeded.

## RedotPay Connect sandbox

The owner-protected endpoint `POST /agent/funding/redotpay/sandbox-checkout` creates a hosted checkout order in the RedotPay sandbox. It returns `pending_payment`, `payment_confirmed: false`, and `ledger_credit_allowed: false`.

Required sandbox settings:

- `REDOTPAY_ENV=sandbox`
- `REDOTPAY_APP_KEY`
- `REDOTPAY_PRIVATE_KEY_PATH`
- `REDOTPAY_KEY_VERSION`

Use provider-issued sandbox credentials and a merchant public key registered in RedotPay's developer console. Store the private key outside GitHub. Read [the complete sandbox guide](docs/REDOTPAY_SANDBOX.md) first.

**A checkout URL is not proof of payment.** Before any future ledger credit, the backend needs a deployed signed webhook endpoint, final-status reconciliation, strict order/user/USD amount/currency matching, replay protection, and idempotent ledger posting. These production crediting operations are not implemented here. A real end-to-end sandbox test still requires provider-issued sandbox credentials and an observed test callback.

## Amazon resale

The current Amazon connector is catalog research only. It requires approved Amazon SP-API/seller access and is disabled by default. It does not place purchase orders, list products, handle customer orders, or guarantee profit. Validate landed cost, fees, taxes, customs, returns, delivery, marketplace policies, and seller eligibility before making business decisions.

## Financial and security boundaries

- User-entered budgets and pending funding requests are not verified money.
- Do not collect or store raw card numbers, CVVs, card passwords, or payment account credentials.
- Do not pool users' funds or allow one user's balance to be spent for another user.
- Never enable production payment processing without written provider approval for the business model and jurisdiction.
- Never enable automatic Amazon purchasing until the official access, user-fund authorization, transaction controls, reconciliation, refunds, and legal/compliance requirements are implemented and reviewed.
- SQLite is suitable for local development, not a concurrent public financial service. Production requires a managed database, migrations, backups, observability, secret management, rate limiting, account recovery, MFA, and independent security review.

## License

See [LICENSE](LICENSE).
