# Deployment guide

## Local/container deployment

1. Install Docker Engine and the Compose plugin.
2. Copy `.env.example` to `.env`.
3. Generate two independent secrets:
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`
   Set one as `AUTH_SECRET`, the other as `ADMIN_API_KEY`.
4. Keep `.env` out of Git. Do not put payment secrets in dashboard fields or chat.
5. Start the app: `docker compose up --build -d`.
6. Check status: `docker compose ps`; logs: `docker compose logs -f commerce-os`.
7. Open `http://127.0.0.1:8000/ui`; API documentation is at `http://127.0.0.1:8000/docs`.
8. Stop: `docker compose down`. The named `commerce_data` volume remains unless explicitly deleted.

The compose port is bound to loopback, not exposed to the public internet. For a public deployment, use a TLS reverse proxy or managed platform, secure secrets, restrict admin endpoints, configure backups and monitoring, and complete the production checklist below.

## Integration activation

The integration endpoint reports configuration readiness only. The provider adapter interfaces are intentionally fail-closed. They do not create payment sessions or orders and must not be represented as live integration.

For every provider:
- Confirm business/country eligibility and obtain the necessary merchant/developer approval.
- Implement the provider's official API contract and authentication for the exact account.
- Validate signed webhook payloads server-side, check amount/currency/order/user binding, reject stale/replayed events, and process idempotently.
- Reconcile provider state after timeouts; a browser redirect is never proof of payment.
- Test declines, duplicate callbacks, refunds, chargebacks, timeouts, invalid signatures and currency mismatches in sandbox.
- Start with read-only access or a sandbox, then a low-limit canary. Keep purchases and balance credits disabled until reviewed.

## Production blockers

This repository is an MVP, not a regulated wallet or a guaranteed-return investment service. Before handling public users or real funds, replace SQLite with managed PostgreSQL, add database migrations, rate limiting, email verification, MFA/account recovery, secure cookie/session handling, backup/restore drills, structured monitoring, incident response, provider/legal review and a documented refund/dispute process.

Do not store card numbers, CVVs, one-time codes or bank passwords. A general-purpose card is not an API credential and cannot automatically be charged for arbitrary transactions unless the issuer/provider explicitly supports the authorized flow.
