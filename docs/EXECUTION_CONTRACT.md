# Execution Contract

## Owner-controlled funding
The owner decides when and how much capital to allocate. The application records a funding declaration; it does not initiate a bank transfer or receive funds. Real transfers require a supported payment provider, legal eligibility, and a separate integration.

## Authority tiers
1. Autonomous: research, scoring, internal reporting, supplier lead tracking.
2. Bounded: proposals for purchases and ads within a per-action cap and available cash.
3. Approval required: purchases, external commitments, account changes, refunds outside policy, contracts, and any action that is hard to reverse.
4. Prohibited: exceeding owner-defined caps, bypassing platform rules/KYC, misrepresenting identity, or treating forecast revenue as cash.

## Loss stop
The default stop is 30% of initial capital in a funding cycle. When reached, freeze discretionary spending. Continue legally necessary support for existing customers and obligations. An owner must explicitly review and authorize a new cycle; a deposit does not erase prior losses.

## Reinvestment
Reinvest at most 80% of cleared net profit after refunds, fees, taxes, liabilities, and required reserves. Keep 20% outside the reinvestment budget. Do not use unsettled marketplace funds.

## Idempotency and audit
All proposals require unique idempotency keys. Record the rationale, requested amount, decision, timestamp, and external transaction reference when an approved integration exists. Never retry a payment or order without checking provider status first.

## Production gate
Before real money execution, implement:
- Strong authentication, MFA for the owner, session controls, rate limiting, TLS.
- Secret manager and least-privilege provider credentials.
- Official marketplace/payment/shipping APIs and verified country eligibility.
- Reconciliation against provider statements and webhook signature verification.
- Duplicate prevention, bounded retries, alerting, backups, incident recovery.
- Legal, tax, customs, consumer-protection, and platform-policy review.
- Shadow-mode validation and explicit owner opt-in for each execution class.
