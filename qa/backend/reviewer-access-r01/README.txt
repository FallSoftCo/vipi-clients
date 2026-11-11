Complimentary reviewer access — explicit account configuration

VIPI_REVIEWER_USER_IDS is a JSON array of canonical lowercase, nonzero internal
Vipi user UUIDs (maximum 32), default []. It is separate from WorkOS subject
admission/staging access. No identity supplied by a request selects the grant:
normal authenticated principal lookup determines the internal user ID.
Only existing active, nondeleted, nonsuspended configured accounts qualify.

Each granted base/bot_mini plan returns active:true,
access_source:"review_complimentary", review_access:true, expires_at:null,
trial_ends_at:null. No store transaction, receipt, expiry, trial or renewal is
fabricated. Real provider records and ordinary revocation/freshness behavior
remain intact. Removing configuration removes complimentary access on subsequent
server checks; real store access, if any, is still independently evaluated.
Configuration does not provision an account or enable a provider.

Bot consent, context limits, provider availability, per-user/global spend,
monthly replies, request identities and account safety use the same paths.
Bot allowance remains service_ready:false without the actual provider key.
Tests use httpx.MockTransport only; no external provider was contacted.
No account/configuration was changed and no full-access attestation is made.

Apple recognizes the exact coherent marker for truthful review-access copy and
omits the misleading payment/renewal statement for that grant. Existing active
server access semantics and bot readiness are unchanged. Actual native Swift
model extraction was executed; partial/unknown markers do not get review copy,
string Boolean fails decoding, and expiry/trial dates cannot represent review
access. SubscriptionView received syntax parsing only, not a full app build or
visual qualification. The existing6ceaf unsigned archive remains preserved and
does not include this change. Android's matching model/copy is owned separately.

Activation requires separately approved verified reviewer IDs and normal service
configuration/deployment. Reviewers need access to the same features and consent
flow; no hidden feature or frontend reviewer-only functional path is added.
