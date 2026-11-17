# Store notifications and subscription reconciliation

Ordinary chat must not depend on an Apple or Google billing request every five
minutes. The service accepts authenticated store notifications, records a
deduplication receipt and schedules a current-status check. New purchases and
explicit restores still require immediate provider verification before access.

`POST /v1/store-notifications/apple` accepts the Apple V2 `signedPayload`. The
official pinned App Store Server Library verifies the outer signature,
environment and application, then verifies any inner transaction. The existing
original transaction identifies a grant to reconcile. A notification never
creates an account or directly changes an entitlement. Configure the production
and sandbox endpoint against their respective verifier environments; a
production verifier does not accept sandbox purchases.

`POST /v1/store-notifications/google` accepts a wrapped Pub/Sub push. It verifies
RS256 through Google's pinned JWKS endpoint, issuer, expiry, audience, verified
service-account email and exact Pub/Sub subscription. It also checks the
decoded package name. Subscription and voided-purchase tokens identify existing
grants by SHA-256; the plaintext token is not retained in a notification record.
Tests and unsupported purchase categories are acknowledged without a grant.
Unknown purchases are acknowledged without creating one: initial purchase or
restore must obtain current provider state. Deleted accounts cannot be restored
by a late event.

Set all three Google values together:

```
VIPI_GOOGLE_RTDN_AUDIENCE=https://api.mambovipi.app/v1/store-notifications/google
VIPI_GOOGLE_RTDN_SERVICE_ACCOUNT=<dedicated Pub/Sub push service-account email>
VIPI_GOOGLE_RTDN_SUBSCRIPTION=projects/<project>/subscriptions/<subscription>
```

The push identity is separate from the Android Publisher API verification
credential. Grant only the documented Pub/Sub token-creation and topic publish
permissions required for those identities; no broad project-admin role is
required. Endpoints return 503 until their store verifier/configuration exists.
Only a committed notification receipt returns success. Exact retries are
idempotent; a reused event ID with a changed fingerprint is rejected. Receipt
identifiers and hashes expire after 30 days, without raw payloads or tokens.

Apply migration `20261107_05`, then install the standard
`ops/vipi-billing.service` and `.timer`. Each invocation performs at most 128
reconciliations, four at a time, with a 45-second dispatch budget. The service
has a 90-second execution bound, one CPU quota and 256 MiB memory bound. Database
leases expire after two minutes if execution stops. Notifications that arrive
during a store call increment a generation; the earlier result cannot discard
that newer work. Failure backs off up to one hour without making chat requests
repeat the store call. The timer runs 30 seconds after completion.

Periodic reconciliation defaults to 24 hours. Existing verified, unexpired
access survives a temporary provider outage for at most 72 hours since its last
successful verification, and never beyond the store's actual expiry. A verified
refund/revocation takes effect when the worker applies it. This explicitly
accepts bounded revocation delay during an outage rather than disconnecting all
paying users after five minutes. Past that bound the service returns unavailable,
not a new paywall. Local history remains accessible. Expired grants are checked
for seven days to catch a delayed renewal; later store events can still enqueue
reconciliation. Superseded grants stay superseded.

The PostgreSQL tests cover real RSA authentication, wrong issuer/audience/email,
forged/expired tokens, duplicate/conflicting event IDs, durable invalidation,
concurrent lease claims, a new event during verification, outage backoff,
expiry and migration consistency. Apple adapter tests exercise the official
verifier call boundary with fixtures; they do not establish a real Apple event.

The actual Apple Sandbox TEST notification passed on November 9, 2026: Apple
reported SUCCESS, the official SDK verified the V2 signature and the matching
event was retained without creating an entitlement. The existing restricted
staging service now uses the Sandbox verifier; the production callback is unset.
See `qa/backend/apple-sandbox-notification-r01/receipt.json`.

A single Google Play test was followed by an authenticated Google receipt; no
entitlement was created. See the [activation and test receipt](../qa/backend/google-rtdn-activation-20261117-r01/receipt.json)
for timing and correlation limits. The Pub/Sub metric records one webhook HTTP 204
in the test minute, without an independently matched message ID.

Release qualification still requires production provider configuration, real
store sandbox purchase/renewal/refund/restore events
and confirmed account binding. Credentials or passing unit tests alone do not satisfy those gates.
Monitor worker failures and pending reconciliation age; no external alert
recipient or staffed response is established by this implementation.

Primary references: [Apple V2 notifications](https://developer.apple.com/documentation/appstoreservernotifications/app-store-server-notifications-v2),
[Apple setup and test delivery](https://developer.apple.com/documentation/storekit/enabling-app-store-server-notifications),
[Google RTDN lifecycle](https://developer.android.com/google/play/billing/lifecycle),
[Google event reference](https://developer.android.com/google/play/billing/rtdn-reference),
[authenticated Pub/Sub push](https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions).

On November 17, restricted staging activated backend `9b8cca6` and migration
`20261116_01` with account-scoped sandbox mode enabled. The initial empty tester
allowlist was later updated to one independently verified non-reviewer tester;
see the [activation receipt](../qa/backend/company-tester-sandbox-20261117-r01/receipt.json). Its [sanitized receipt](../qa/backend/store-sandbox-deploy-20261117-r01/receipt.json)
records the two earlier verified rollbacks and the successful deployment; do not
replay those attempts. Existing reviewer grants and the FCM push worker remain
unchanged. The account-scoped tester must be an independently verified,
non-complimentary account. Real purchases, renewal, restoration and RTDN remain
unqualified, and subscription enforcement remains disabled in restricted staging.
Later homepage and APNs worker source changes are not part of this deployed
backend. A future rollout must recheck the live revision, schema, configuration,
backup and service state before action.
