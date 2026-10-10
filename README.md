# Autonomous Commerce OS

A risk-controlled foundation for an AI-assisted ecommerce operator. It is designed to grow from product research into supplier workflows, order operations, and approved platform integrations.

> **Important:** This repository is an MVP/control plane, not a live autonomous money manager. No payment provider, Amazon Seller Central, AliExpress, Alibaba, or shipping account is connected by default. Purchases and money transfers are not executed. Start in simulation mode; connect only official APIs after eligibility, legal, and security review.

## Core capabilities
- Owner-defined, changeable budgets recorded as auditable ledger entries.
- Risk policy with a loss stop calculated against the initial capital for each funding cycle.
- 80% reinvestment policy reserved for realized, cleared, available net profit after liabilities and reserves.
- Product opportunity scoring with explicit component scores.
- Purchase proposals with idempotency keys, per-action limits, and approval gates.
- Simulated supplier/order workflows and an audit trail.
- API endpoints suitable for a future dashboard and background worker.

## Quick start
Python 3.11+ recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app:app --reload
```

Open http://127.0.0.1:8000/docs for the API.

## Safety defaults
- `EXECUTION_MODE=simulation` by default.
- No card, bank, wallet, or marketplace credentials are accepted by this MVP.
- A proposal cannot spend more than the available unreserved cash, action cap, or current cycle loss limit.
- Irreversible or regulated actions require owner approval.
- A loss stop freezes new discretionary spending, not customer support, refunds, legal duties, or fulfilment obligations already accepted.
- The API is intended for local development. Put it behind authentication, TLS, rate limiting, and a secrets manager before exposing it to a network.

## Budget and accounting rules
A funding cycle starts when the owner records a deposit. The loss limit is 30% of that cycle's initial capital by default. A new deposit does not silently erase earlier losses; create a new cycle only with an explicit owner action and retain the complete ledger history.

Reinvestment is calculated from cleared net profit only. Sales revenue is not profit; unsettled marketplace balances and expected refunds are not available cash.

## Product scoring
The score combines demand, competition, margin, supplier reliability, fulfilment fit, and compliance risk. Scores are decision support—not verified market data or a promise of sales. Populate inputs from lawful, current sources and keep source timestamps.

## Roadmap
1. Validate seller eligibility, payout rails, tax, customs, and fulfilment from the owner's jurisdiction.
2. Add authenticated owner dashboard and background task queue.
3. Add market-data providers and supplier CRM.
4. Integrate official Amazon SP-API and approved supplier/shipping APIs with least-privilege credentials.
5. Add payment workflows only through a regulated provider that supports the business and country; never store raw card data.
6. Run in shadow mode, compare recommendations with real outcomes, then enable tightly capped actions.

## Tests
```bash
pytest -q
```

## License
MIT
