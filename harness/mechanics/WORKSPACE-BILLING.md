# Workspace billing

`workspace_billing.py` owns workspace subscriptions and verified credit-payment receipts. The server owns authentication, route registration and private configuration; the existing CompanyUsage ledger owns usage money. A vertical supplies its server-assigned price.

## Host contract

Construct `WorkspaceBilling(state, environment_id=..., company_id=workspace_scope(state), config=..., provider=..., webhook_secret=..., credit_receipt=...)`. Configuration is a trusted server record, separate from credentials:

```json
{
  "schema_version": 1,
  "environment_id": "demo",
  "company_id": "THE_WORKSPACE_SCOPE",
  "mode": "subscription",
  "account_id": "acct_COMMISSIONED",
  "livemode": false,
  "customer_id": "cus_COMMISSIONED",
  "subscription_id": null,
  "price_id": "price_ASSIGNED",
  "allowed_price_ids": ["price_ASSIGNED"],
  "return_url": "https://workspace.example.test/?view=billing",
  "grace_seconds": 0,
  "max_staleness_seconds": 86400
}
```

A standard vertical price and a customer-specific price use the same explicit `price_id`. The browser submits a request ID, never a customer, subscription, amount, price or return URL. Optional fields: `portal_configuration_id`; `credit_pack: {"price_id": "price_CREDITS", "amount_usd": "5.000000"}`. An explicit `mode: "demo"` requires `demo_expires_at` (UTC ISO timestamp or Unix seconds); Stripe fields may be omitted until commissioning. Demo entitlement and subscription evidence remain separate. Config absence leaves `require_operational()` permissive for existing verticals.

`StripeHTTPProvider(secret_key, account_id=..., livemode=...)` sends bounded HTTPS requests to Stripe only, checks the account identity, pins API `2025-03-31.basil` and verifies object mode. Secrets remain outside status output. Account ownership must be commissioned independently: account-ID agreement proves the configured key's account, not its commercial owner.

Methods are synchronous; call from `asyncio.to_thread` in HTTP handlers:

- `status()` / `access()` return `operational`, `reason`, demo expiry, current subscription, checkout/portal/credits availability, the existing usage summary and `agent_work`.
- `checkout(owner=server_is_owner, request_id=..., kind="subscription"|"credits")` returns a hosted session ID/URL. Repeating a request reuses its receipt; an existing open subscription checkout is reused. A failed creation keeps its original idempotency key. An uncertain request older than 23 hours requires reconciliation before retry.
- `portal(owner=server_is_owner, request_id=...)` returns the server-bound customer's hosted portal. Configure its Stripe portal features for invoices and card updates.
- `handle_webhook(raw_bytes, stripe_signature)` validates a snapshot webhook body up to 256 KiB, persists its hash, and processes exact known objects. Subscribe to `customer.subscription.*`, relevant `invoice.*`, `checkout.session.completed` and `checkout.session.async_payment_succeeded`. Retries reuse the original event; provider failure leaves it pending for a retry.
- `reconcile()` refreshes the bound subscription. The shared HTTP host reconciles at most hourly after success and retries after one minute on failure, also checking on admission; status itself is a local read. Every reconciliation and webhook serializes canonical Stripe retrieval and projection writes using a workspace lock, so out-of-order event bodies cannot overwrite current provider truth.
- `require_operational()` is suitable for `ManagedPolicy._require` before normal and delegated paid work. It checks entitlement, while existing ManagedUsage/CompanyUsage reservations check spendable credits. Checking a free-balance flag inside an admitted turn would incorrectly reject its own reserved allowance.

Keep login, session recovery, billing status, checkout, portal and signed billing ingress reachable when operational access is blocked. Derive the owner flag from the current authenticated workspace role. A successful return redirect grants nothing.

## Admission and funds

Active/trialing subscriptions allow work until the observed service/trial end, bounded by maximum observation age. Cancellation at period end preserves that interval. Past-due grace begins at the first persisted observation and survives repeat events/restarts. Unpaid, canceled, incomplete, incomplete-expired and paused states block operational access. Invalid canonical customer/mode/price evidence withdraws the cached entitlement.

Empty AI credits leave human CRM available. `usage_credit_callback(state)` applies only live, paid, company-bound receipts to the existing selected agent pool. Canonical Checkout and PaymentIntent/charge must agree; refunded/disputed payments are held. Event, checkout and payment deduplication preserve one funding event across retries and a crash after ledger commit. Credit sinks must preserve the same idempotent receipt key contract. The existing ledger's monthly cap still applies, and its operator/demo allowance cannot be mixed with customer prepayments. Live credit checkout is held until that pool is suitable.

## Commissioning limits

All current proof uses synthetic records and mock HTTP; no Stripe account or charge was commissioned. Match snapshot webhook version to the adapter pin. Reconcile expired/uncertain checkouts operationally. A fully canceled prebound subscription needs an explicit replacement binding before a new subscription. Later refunds/chargebacks require operator reconciliation of already-applied credit receipts; automatic reversal is outside this first module. Keep optional paid credit packs uncommissioned until that operational path is selected.

Official references: [Stripe versioning](https://docs.stripe.com/api/versioning), [subscription retrieval](https://docs.stripe.com/api/subscriptions/retrieve?api-version=2025-03-31.basil), [webhook verification and delivery](https://docs.stripe.com/webhooks), [hosted portal session](https://docs.stripe.com/api/customer_portal/sessions/create).
