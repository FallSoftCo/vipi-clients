# Vipi-only deletion contract — source revision, not deployed

`DELETE /v1/me` and the same-origin `/delete-account` confirmation erase Vipi
records in one database transaction. They never call WorkOS user DELETE, whether
the configured identity pool is shared or dedicated. `WorkOSUserDeleter` and the
provider-job dispatcher are removed. Normal maintenance only expires completed
seven-day status receipts. Existing unfinished legacy jobs retain their state
and are **not** executed, relabeled complete, or rebound to the current provider
environment. An operator must reconcile those exact historical requests before
any separate cleanup. There is no global Fallsoft deletion endpoint here.

The API retains its 202 response and existing `account_id`/`status` shape; newly
completed app-only requests return `status: deleted`. The native 256-bit receipt
continues to authorize status independently of a bearer. Raw provider subject
and receipt secret are absent from completed rows. Wrong capabilities remain
404. Receipt retention is seven days and does not prohibit rejoining.

Fresh explicit authentication, no more than ten minutes old and strictly after
the last deletion timestamp, permits a new Vipi profile immediately. A freshly
issued access token with an old authentication time does not satisfy this rule.
The new profile has a new internal UUID and a persisted `minimum_auth_time`.
All profile-authenticated HTTP paths and foreground WebSockets reject older
sessions, including after old deletion receipts expire. New-profile creation
still requires recent sign-in when no receipt remains. Existing migrated users
start with an authentication floor of zero; no unrelated sessions are revoked
by the migration itself. A signin in the same second as deletion must be
repeated in a later second because authentication claims have integer precision.

Deletion retries bind **account UUID, keyed subject hash and receipt**, before
looking at any newly joined profile. Replaying an old deletion returns the old
receipt and cannot erase the new UUID. Distinct old receipts can coexist under
one subject hash. Browser receipts select their original account UUID. An
unfinished-profile browser receipt can observe a concurrent native deletion
with another provisional UUID; it cannot target a newly created profile. An
explicit new browser sign-in reviews the current profile instead of forcing the
old receipt forever. A restored history can likewise contain multiple deleted
UUIDs for one subject; per-account evidence conflicts still fail atomically and
all existing offline recovery holds remain in force.

`vipi_trial_eligibility` contains only an HMAC subject key and original trial
start/end timestamps. It stores no raw identity, profile, messages, purchase,
or device. Existing users' dates are captured before deletion; new registrations
consult the ledger. Deleting and rejoining does not restart or extend the free
period, even after receipt expiry. This record is intentionally retained while
the shared Fallsoft account exists. The separately authorized global workflow
must invoke `vipi.eligibility.erase_for_global_fallsoft_deletion` against Vipi's
own database and exact subject/key authority. That hook only erases eligibility;
it does not claim to delete shared identity or other apps. Its global caller is
not implemented by this app-only change. Identity linking and service-key
rotation must preserve original eligibility across authorities/keys; they must
not silently create a new free period.

Paid entitlement rows are erased with Vipi, and store subscriptions are not
canceled. Existing purchase proofs remain bound to the old account UUID and
store account token. They are **not** automatically transferred to the new UUID.
A separately reviewed, verified restore/link policy is needed; no email-only
merge, reassignment, complimentary paid grant or store operation is added.
Verified self-service restoration after rejoin is a release gate: this revision
must not be deployed in a way that makes existing subscribers repay or leaves
them with an invented support route. Public copy says to cancel subscriptions
through the app store and discloses retained trial eligibility. Copies kept by friends, local device histories, user-exported
backups and historical service backup retention keep their existing boundaries.

## Migration and rollback preparation

Migration `20261117_02` follows `20261117_01`, adds the authentication floor and
minimal ledger, and replaces receipt subject uniqueness with a nonunique index.
It makes no provider calls, changes no old pending-job state and does not copy
raw subjects into the ledger. The readiness check requires the new exact head.
Before a future deployment, stop any old provider-deletion executor, reconcile
its actual running/uncertain request receipts, preserve an exact database backup,
run the migration and verify readiness using the new service code. These are
preconditions, not authorization to stop services or deploy.

Downgrade refuses to discard populated eligibility, a nonzero authentication
floor or multiple receipts for one subject. A rollback after those exist must
retain the new schema/guards and use compatible code; do not run old provider
cleanup workers or erase protective rows to force downgrade. An empty-state
schema downgrade remains available for isolated qualification. No production
migration, provider deletion, account deletion or service restart was performed
while implementing this revision.

Offline recovery evidence can now retain exact HMAC-keyed original eligibility
records produced after a snapshot; conflicts fail atomically. Marked recovery
coverage requires an additional `eligibility` domain bound to the same snapshot
and cutoff. Older five-domain proof packages are intentionally insufficient.
Reconciliation still never releases the database hold or authorizes reopening.


Actual isolated PostgreSQL 16 qualification passed all 38 deletion, browser,
lifecycle-concurrency and migration tests after the copy followup. The retained
owned Unix-socket-only qualification cluster was reused; disposable per-test
schemas were removed and no other clients remained before its clean shutdown.
Measured peak cluster growth was 5,857,280 bytes under the 100 MiB cap; the
4 GiB + 200 MiB reserve remained intact. See the adjacent PostgreSQL receipt.
No shared/live PostgreSQL instance, deployment or provider identity was touched.
