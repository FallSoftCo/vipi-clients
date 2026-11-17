# Cardless Base trial — restricted staging rollout

The server grants Base access for exactly 30 days from each profile's persisted server creation time. No store purchase or automatic renewal is created. The independent Bot mini entitlement remains required for Bot access. The trial remains visible separately when a verified paid store entitlement or complimentary reviewer access takes precedence.

Migration `20261117_01` derives existing accounts' immutable trial start from their original `users.created_at` and end 30 days later; it never grants a fresh interval merely because the migration runs. Existing owned staging accounts follow the same rule. Profile creation, retries and device replacement do not reset it. Account deletion removes user data and the existing subject-deletion lifecycle blocks same-subject re-registration while its tombstone is retained; a later distinct identity can obtain another trial. Existing account/rate and deletion policy do not guarantee deduplication across identities. This is not a promise of permanent anti-abuse identity retention.

The restricted staging backend was activated once on 2026-11-17 at 04:56 UTC: release `84c3ff8db5235a0b9419373f5d56b99ad50bf495`, schema `20261117_01`. An isolated PostgreSQL upgrade/downgrade/re-upgrade rehearsal and a fresh activation-time backup preceded the coordinated API/billing drain. All seven existing accounts retained trial dates derived from their original creation times. Push, configuration, reviewer access and the restricted registration policy were preserved. This does not enable public signup, customer enforcement or a store release.

Independent verification confirmed private readiness, authenticated-endpoint rejection without credentials, updated public policy pages, restored billing/expiry timers and unchanged shared services. The public readiness endpoint deliberately returns 403 under the unchanged nginx policy; it is not a rollout failure. The original activation ledger and independent postcheck are retained under `investigations/vipi-submit-20261110-r01/backend-cardless-activation-prep-20261117-r01/`. Do not repeat the activation or restore its database backup merely to check status.

Before public launch: finish native client qualification, remove the old Base store introductory offers on both platforms, and verify the final release and store lifecycle. Store offers and uploaded clients were not changed by this rollout. Downgrade drops the trial columns; because v1 derives both dates strictly from original account creation, re-upgrade reconstructs the same dates provided `created_at` is preserved. Do not downgrade across future policy changes without new review. Existing paid purchases and separate Bot mini offers are not reinterpreted as trial grants. Validate access at the exclusive expiration boundary, restore/deletion/local-history behavior, and a real store lifecycle before enabling customer enforcement.

Native response examples and scope: `backend/qa/cardless-trial-contract-v1.json`; server time governs. The fixture is not a live rollout receipt; the independent deployment evidence is recorded in `qa/subscriptions/cardless-trial-20261117-r01/receipt.json`.


Proposed source revision `20261117_02` (not deployed by this change) replaces
that app-deletion tombstone ban with fresh explicit sign-in and a new profile.
It retains only a keyed eligibility hash and the original trial dates across
Vipi deletion/rejoin, so rejoining does not restart or extend the original
period. See `vipi-only-deletion-20261117.md` for the exact migration, retention,
stale-session and separate global Fallsoft-deletion boundaries. The activation
receipt above describes the earlier deployed revision and is unchanged.
