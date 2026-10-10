# VZX Field Agent — architecture and activation plan

## Product goal

A USD-denominated commerce operator that researches products, evaluates suppliers, calculates landed unit economics, tracks orders and reconciles actual net profit. It should be ambitious in opportunity discovery and conservative about irreversible actions.

## Current branch implementation

- `agent_engine.py`: deterministic opportunity scoring, all-in per-unit cost calculation, spend caps, loss-stop evaluation, and audited profit-alert formatting.
- `integration_registry.py`: reports whether provider environment variables are present. It intentionally reports `live_enabled=false` even if credentials exist.
- `tests/test_agent_engine.py`: tests the decision engine and guardrails.
- Existing platform API and task queue remain the user/account boundary. This addition does not yet create a live marketplace worker or payment integration.

## Agent operating loop

1. **Discover:** obtain product candidates from approved data APIs or user-provided data; record source and timestamp.
2. **Verify supplier:** identity, history, MOQ, delivery time, return terms, counterfeit/IP risk, and sample order evidence.
3. **Calculate:** product cost + shipping + customs/tax estimates + marketplace/payment fees + fulfillment + returns reserve + ads/customer support.
4. **Gate:** reject prohibited/high-compliance-risk products; require verified available budget; enforce order cap, cycle loss stop, and duplicate-order idempotency.
5. **Propose:** persist a decision with evidence, uncertainty, and a maximum all-in cost.
6. **Execute:** only through official provider APIs with explicit scoped authorization. Use dry-run/sandbox first. For irreversible purchases, require an approved policy and a human confirmation until production controls are independently tested.
7. **Reconcile:** match provider events, order, settlement, refunds, fees, and supplier invoice. Never infer realized profit from expected margin.
8. **Notify:** emit profit alerts only after payment settlement and full cost reconciliation. Notifications may report losses, pending orders, stockouts, refunds, and blocked actions too; do not manufacture gains to make the feed busy.
9. **Learn:** evaluate conversion, return rate, supplier reliability, stockouts, net margin, and forecast calibration. Do not optimize only for gross revenue.

## Card and payment boundary

Do not ask users to send card numbers, CVV, bank passwords, or one-time codes to the agent. Do not store raw card data. Prefer a provider-hosted checkout and, where available and contractually permitted, a tokenized/virtual card or spending-control product. A card is a funding source, not a general-purpose API credential. The card issuer may reject off-session purchases, recurring/foreign transactions, merchant categories, or transactions requiring authentication.

The user-specified budget is a *policy limit*, not proof of available funds. Keep these separate:
- declared budget;
- provider-confirmed funding/payment;
- available-to-spend amount after pending authorizations;
- reserved amounts for open orders;
- settled costs, refunds, and net realized P&L.

A payment integration must verify server-to-server signatures, amount, currency, merchant/order/user binding, event ID, status, duplicate delivery, refunds, and disputes before changing a ledger. Browser redirects never credit money. Keep all internal monetary records in USD and use decimal arithmetic, not binary floating-point.

## Integration configuration

Copy `.env.example` and set provider credentials in the deployment platform's secret manager, never in source control. The registry is diagnostic only. Before enabling a connector:
- confirm provider availability for the actual business country and entity;
- obtain required merchant/developer approvals;
- implement official OAuth and least-privilege scopes;
- implement signed webhook validation and replay/idempotency protection;
- test declines, duplicates, timeouts, partial refunds, chargebacks and currency mismatches in sandbox;
- complete security and legal review.

Amazon SP-API requires developer registration, application registration, and seller authorization appropriate to the application type. Marketplace/supplier credentials are not interchangeable with a card credential. Do not bypass platform restrictions, anti-bot controls, seller verification, or geographic eligibility.

## Live activation checklist

- [ ] Production database with transaction isolation and backups (PostgreSQL recommended).
- [ ] Authentication hardening: email verification, MFA, rate limits, secure session/token rotation, account recovery.
- [ ] Independent user and tenant isolation tests.
- [ ] Signed webhook handlers and a replay-safe payment ledger.
- [ ] Explicit per-order, per-day and per-cycle limits, including pending authorizations.
- [ ] Kill switch, circuit breaker, timeout/retry policy and duplicate-order prevention.
- [ ] Auditable approval records and least-privilege credentials.
- [ ] Reconciliation job, monitoring, alerting and disaster recovery.
- [ ] Sandbox test suite and controlled canary before any live funds.
- [ ] Provider eligibility and legal/compliance review for the operating entity and countries.

## Reality check

This branch adds an analysis/guardrail foundation, not a money-making guarantee. There is no proven strategy that reliably turns small capital into a stream of positive daily returns. A product score is a ranking aid, not a prediction. Live payments, card control, supplier orders, Amazon listings, shipping and profit reconciliation require approved provider accounts and separately implemented adapters.
