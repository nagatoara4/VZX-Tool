# Integration and go-live plan

## What is implemented now
- Per-user accounts, password hashing, signed expiring bearer tokens, isolated budget cycles, ledger entries and purchase proposals.
- Budget declarations are explicitly marked `pending_payment`; they never count as cash.
- A durable task queue for research/report/reconciliation work.
- An integration status endpoint that reports only whether environment variables are present.
- No real money movement, inventory purchase, listing publication, or customer order execution is enabled.

## Payment providers
Set up a business account with a regulated provider that explicitly supports the operator's country, legal entity, business model, currencies, customer countries, refunds, and payouts. Do not use a personal account or misrepresent location. This project intentionally does not credit a balance based on a browser redirect or client-supplied event. A payment adapter must:
1. Create a provider-hosted checkout/session server-side.
2. Verify the provider's signed webhook using the raw request body and secret.
3. Validate the event ID, payment status, amount, currency, merchant account and expected user/cycle.
4. Be idempotent and reconcile against provider records.
5. Record refunds, disputes, fees and chargebacks as separate ledger events.
6. Keep customer money segregated and never treat pending payments as spendable cash.

The product currently has no live payment endpoint. `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `PAYPAL_CLIENT_ID`, and `PAYPAL_CLIENT_SECRET` are detection flags only, not a claim that either provider is available for this use case. Verify country and business eligibility directly with the provider before implementation. If the business model involves holding or investing customer funds, obtain local legal/regulatory advice first.

## Amazon Seller / SP-API
The environment flag requires `AMAZON_SP_API_REFRESH_TOKEN`, `AMAZON_SP_API_LWA_CLIENT_ID`, and `AMAZON_SP_API_LWA_CLIENT_SECRET`. This is not a working connector by itself. Real use also requires an approved SP-API application, correct roles/scopes, seller authorization, regional endpoint selection, IAM/signing where applicable, data-protection review, rate limits and sandbox/live tests. Use the official Amazon SP-API documentation and do not scrape or bypass marketplace controls.

## AliExpress / Alibaba suppliers
API access is account- and program-dependent. Credentials alone do not imply approval or access to product/order APIs. Request access through the official supplier platform, use authorized endpoints, store secrets only in the hosting provider's secret manager, and test against sandbox or non-financial calls before live order operations.

## Shipping and fulfilment
A shipping adapter must provide serviceability, quoted cost, tracking, cancellation, delivery exceptions and claims. Do not promise a dispatch date until stock and carrier confirmation are available.

## Production security checklist
- Replace local SQLite with managed PostgreSQL before concurrent public production use.
- HTTPS, rate limiting, email verification, password reset, MFA, CSRF protections for cookie sessions, and abuse monitoring.
- Secret manager; never commit `.env`, tokens, card data or customer PII.
- Database backups, migrations, retention and data export/deletion procedures.
- Signed webhooks, replay protection, idempotency keys and reconciliation jobs.
- Unit, integration, failure-mode and authorization-isolation tests.
- Human approval gates for purchases, refunds, listing changes and external commitments.
- Independent legal, tax, customs, privacy, marketplace and payment-provider review.

## Enablement sequence
1. Deploy in simulation mode.
2. Verify jurisdiction/business/payment eligibility.
3. Complete official provider app approvals and store secrets in the host environment.
4. Implement and test one connector at a time in sandbox.
5. Run shadow mode and reconcile proposed actions against source systems.
6. Enable only explicitly authorized action types with low per-action caps, monitoring, a kill switch and rollback.
