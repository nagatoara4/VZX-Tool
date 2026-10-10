# RedotPay Connect sandbox integration

## Scope and important distinction

This connector creates a RedotPay Connect hosted checkout in sandbox for a user funding request. It is a **merchant collection flow**, not a programmable card or an API that spends from a user's RedotPay/Visa/Wise card. It does not buy products from Amazon, and it never credits a balance based on a browser redirect.

Keep separate per-user accounts and ledgers. A successful order-create response means only that a checkout was created. Before a future production ledger credit, the backend must verify the provider callback signature, confirm final payment status through the official order query/reconciliation API, match merchant order ID + user + exact USD amount + currency, and enforce event/order idempotency. Browser redirects are never authoritative.

## Configure a sandbox account

1. Complete RedotPay merchant onboarding and request developer access.
2. In RedotPay Connect, switch to sandbox and register the merchant public key.
3. Keep the matching RSA private key outside the repository; configure its file path as a runtime secret.
4. Set `REDOTPAY_ENV=sandbox`, `REDOTPAY_APP_KEY`, `REDOTPAY_PRIVATE_KEY_PATH`, and `REDOTPAY_KEY_VERSION` to the version registered with RedotPay.
5. Install dependencies and run `pytest -q`.
6. With provider-issued sandbox credentials configured, call `create_sandbox_checkout(...)` from an authenticated, owner-approved local test path and inspect the returned HTTPS hosted checkout URL.

The client hardcodes the documented sandbox host and refuses `REDOTPAY_ENV=production`. Do not commit `.env`, PEM private keys, app keys, webhook secrets, or customer payment data.

## Request signing and callback verification

The request signature string used by this client is:

```text
POST /openapi/v2/order/create
{appKey}.{timestampMs}.{compactJsonBody}
```

It signs with RSA PKCS#1 v1.5 + SHA-256 and Base64. Callback verification is a cryptographic primitive only; the eventual webhook endpoint must also validate event schema and terminal status, merchant order, user mapping, exact amount/currency, replay protection and idempotency before any ledger mutation. Use the provider's platform public key and key version for the matching environment; sandbox and production keys are distinct.

## Sandbox versus production

Unit tests can verify signing and fail-closed behavior without a provider account. A real end-to-end sandbox test still requires RedotPay-issued sandbox credentials, a registered merchant public key, network access from the runtime, and a test checkout/callback. Do not claim the provider sandbox passed until a real sandbox request and callback have been observed.

Production remains blocked. Before considering it, obtain written RedotPay approval for the merchant and user-funding model, confirm country eligibility, complete compliance review, implement signed webhook ingestion plus order reconciliation and idempotent per-user ledger posting, conduct a security review, and explicitly approve a release. Even an approved payment-collection path does not authorize purchases on Amazon.

## Amazon resale

Amazon SP-API is a separate integration and requires approved developer/seller authorization. SP-API sandbox calls return mock/static data for supported operations; they do not validate real demand, purchasing power, legal eligibility or resale margin. Keep catalog research read-only. Product purchasing/listing and customer-fund spending remain disabled until Amazon's official access and a compliant order-execution design are separately approved.

## Official references

- [RedotPay Connect getting started](https://redotpay.readme.io/docs/getting-started)
- [RedotPay Open API v2 create order](https://redotpay.readme.io/reference/createprepayorder-1)
- [RedotPay request signature and callback verification](https://redotpay.readme.io/docs/redotpay-api-request-signature-and-verification-guide)
- [RedotPay Open API v2 upgrade guide](https://redotpay.readme.io/docs/open-api-v2-upgrade-guide)
- [Amazon SP-API sandbox](https://developer-docs.amazon/sp-api/lang-en_en/docs/sp-api-sandbox)
