# Offline recovery reconciliation — isolated implementation

Implemented in new `backend/vipi/recovery.py` and `ops/reconcile-recovery.py`; eight synthetic disk-backed tests pass. No existing API, configuration, schema/migration or deployment files changed. No live database, backup decrypt, provider call, service restart or credential change occurred.

## Existing evidence and gap

The retained `backend-backup-enrollment-r01/local-restore-receipt.json` demonstrates authenticated decryption, tamper rejection, equal counts for 20 tables, four device credentials deactivated and entitlement freshness cleared. It explicitly does not accept live recovery. It had zero deletion, moderation, entitlement and spend rows, so did not exercise later-event reconciliation.

Current deletion receipt expiry is seven days after completion (`deletion.py`); restrictions and spend/request identities are in the same backed-up database. No independently complete post-snapshot interval was located in this scoped audit. Clearing entitlement freshness blocks stale access, but subsequent store verification cannot recover absent spend or consumed request IDs. The existing code can therefore not safely infer reopening from a successful restore.

## Input/output contract

Evidence schema 1 binds a snapshot SHA-256, aware snapshot/cutoff timestamps, the operator's `claimed_complete` assertion, and bounded deletion/restriction lists (at most 1,000 each). Original deletion account/subject/receipt hashes and cleanup state are retained. No receipt credential is synthesized. Restrictions contain account ID, suspended state and observation time. Duplicate identities, conflicting receipt identities, future cutoffs, timestamps beyond cutoff and mismatched snapshot hashes fail. A cutoff older than the actual latest authoritative event cannot be detected from this input alone.

These records and claimed completeness are **not proof of authenticity, completeness, ordering against unseen events, or an independently verified cutoff**. The tool never verifies an external authority or signature. Older restrictions are not cleared by supplied appeals; those require separately verified current authority. Missing identities are counted, not fabricated. Account deletions take precedence.

In one transaction the reconciler:

- Erases supplied deleted accounts and related records, preserves supplied original deletion receipt identities, and never changes completed cleanup back to pending.
- Applies suspensions only; refuses to lift a restriction from supplied assertions.
- Deactivates every remaining device; clears entitlement freshness/leases and deletion worker leases.
- Removes excluded relay/key/push/report content even if the supplied snapshot had incorrect exclusions.
- Retains personal spend, uncertain reservations and consumed request IDs for surviving accounts. Required account erasure removes personal records; global spend/reserves remain unchanged.

Every report says `authority_verified=false`, `interval_complete_verified=false`, `reopen_authorized=false`, `bot_dispatch_authorized=false`, `runtime_gate_installed=false` and `services_must_remain_stopped=true`. These are **report conclusions, not enforcement hooks**. Missing post-snapshot charges/requests are not invented, and no claim is made that the existing running API would reject them. API and workers must not be started on this copy.

The CLI accepts only a regular bounded offline SQLite file, not a PostgreSQL/service URL. It rejects SQLite sidecars, checks the supplied hash, creates a new exclusive private output directory/copy, verifies integrity, and leaves the input unchanged. It does not decrypt or restore a production PostgreSQL archive. Its report/receipt record hashes and counts without account IDs on stdout. SQL exceptions are reported by type only. Failed copies/receipts remain for inspection; existing output directories are never overwritten. Disk admission requires 8 GiB plus three input sizes and 8 MiB; input limits are 256 MiB DB and 4 MiB evidence. This deliberately small offline adapter is not the production restore runner.

## Validation

The dedicated fixture always creates synthetic SQLite on disk; it does not use the shared fixture's optional PostgreSQL environment URL. Existing retained `backend-env` dependencies were reused, no installation. Final run: **8 passed in 6.40 s**. Initial six tests passed in 4.55 s; two additional tests then checked deletion/global reserve accounting and bad-backup transport exclusion.

Checks cover idempotency, claimed completeness never opening service, conflict-triggered full rollback, original snapshot binding, future/stale-cutoff contradictions, duplicate evidence, refusal to unsuspend, completed-deletion monotonicity, old-device re-registration failure, retained request replay rejection, spend preservation, global reserve survival after personal erasure, excluded transport removal, CLI input immutability and no output overwrite. These are isolated functional checks, not PostgreSQL concurrency, production restore or native re-enrollment qualification.

## Remaining delivery gate / proposed next seam

Before editing existing runtime files, review an explicit recovery-admission design: a restored-service epoch/checkpoint bound to the exact restore and externally verified reconciliation authority/cutoff, checked by API startup **and** deletion/billing/bot workers before serving or dispatching. A Boolean in this report cannot supply that authority. The database schema and API/config hooks are intentionally not implemented here; an enforced gate needs separate review and isolated integration tests showing that every relevant entry point refuses an unresolved epoch.

The external evidence prerequisite remains unresolved: a complete independently retained deletion/restriction interval, current store verification, personal/global spending and consumed-request reconciliation (including uncertainty), then explicit device re-enrollment. If that evidence is unavailable, keep recovery offline. This patch does not make reopening release-ready.

## Subsequent startup hold

`recovery-hold-receipt-r01.json` records the separately reviewed runtime addition.
Set `VIPI_RECOVERY_HOLD=true` consistently in the environment of the API,
billing, expiry/deletion and push processes **before** starting a restored copy.
The held API constructs no database, authentication, store, bot or event clients.
It serves only static product/privacy/help/deletion guidance and liveness;
readiness returns 503, all other HTTP paths return 503 and WebSockets close
before acceptance. Worker entry points return before client construction.
Private operator list/show remain available; operator mutations are refused.

The default is false, preserving ordinary deployments. This startup flag is
not automatic restore detection, a live drain, evidence authority or an epoch
protocol. It cannot stop processes already running with the flag unset. An
offline report never changes it. No live service was changed. The same external
evidence and explicit re-enrollment gates above remain necessary before release.
The focused plus affected default-path regression passed 101 tests; four optional
PostgreSQL-only tests were skipped. Source/log hashes are in the receipt.

## Restore-bound database admission (subsequent isolated implementation)

`Database` now checks for `vipi_restore_hold` on ordinary connection checkout.
Any marker table presence, including empty or malformed contents, refuses the
connection. API lifespan checks admission before starting events; billing,
maintenance/deletion and push workers check before provider construction or
work. Ordinary unmarked databases require no schema migration and remain
unchanged. This supplements the existing opt-in startup hold; it is not a hot
drain and cannot make an already connected, in-place restore safe.

The isolated SQLite CLI now accepts `BoundRecoveryEvidence`: `reconciliation`
is the original evidence object, and `coverage` supplies exactly one record per
`deletions`, `restrictions`, `billing`, `spend`, and `requests`. Each record has
`domain`, `snapshot_sha256`, `start_at`, `cutoff_at`, `artifact_sha256`, and
`claimed_complete: true`. All intervals must equal the supplied snapshot→cutoff.
These are explicit external assertions, not verified authority or proof of
artifact contents/completeness. Referenced billing/spend/request artifacts are
**not applied** by this adapter. The report identifies these unapplied domains,
and every result remains HOLD with reopening and native re-enrollment false.

Before copying, the CLI creates/fsyncs a private HOLD intent. It stages into
`.restoring.sqlite`, commits a snapshot/time/restore-ID-bound database marker,
then atomically publishes `quarantined.sqlite`. Failed copying cannot publish a
final target; failed reconciliation rolls back its data transaction but retains
the separately committed marker and intent. Inputs remain unchanged. The tool
has no release command. An explicit `offline_recovery=True` library handle is
required for reconciliation; no runtime environment flag provides that bypass.

The ordinary connection guard and marker/reconciliation library include a
PostgreSQL dialect, but this change does not implement or qualify the external
fleet PostgreSQL restore runner. That integration must establish a committed
HOLD on a disconnected isolated target before restored data is exposed, retain
it across restore failure, prohibit a dump from replacing/removing the marker,
and bind the actual snapshot and restore identity. Do not substitute the SQLite
CLI for this integration. No PostgreSQL execution, live database access, provider
verification or native disaster re-enrollment was performed in this revision.

Qualification uses a nonzero synthetic disk fixture: later deletion/restriction,
stale devices/entitlement and retained personal/global spend/uncertain request.
It checks held startup/workers, unchanged unmarked behavior, failed-copy intent,
rollback without marker removal, and successful conservative supplied-evidence
application that still cannot reopen. On this host the real CLI's unchanged
8 GiB capacity floor is unavailable, so subprocess capacity tests are skipped;
sub-MiB in-process lifecycle tests explicitly mock only the admission reading.
This is not real-capacity or production restore qualification. Logs and exact
source hashes accompany the new receipt; historical receipts remain unchanged.
