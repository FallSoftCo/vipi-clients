# Independent Groups client/protocol review — November 19

Reviewed clients worktree `e70b8d0e16648c17896ae48b8a8fd436a42d04a3` read-only.
Backend baseline `2d61565d`. These are source findings, not native runtime or
PostgreSQL concurrency qualification. Groups remain disabled and separate from
free one-to-one launch.

## Release blockers

1. **Control and roster mutation are separate commits.** Android
   `GroupsSession.kt:67-70`, iOS `GroupsSession.swift:91-95` send a control and
   advance local approved membership before the separate roster mutation. A
   concurrent rename, invite or membership change can make the mutation's
   `expected_epoch` permanently stale. Recipients can approve a roster that
   never committed; a saved mutation plan continually retries that old epoch.
   Owner leave has the same split at Kotlin 89-90 / Swift 128-129. Required:
   atomic backend mutation plus exact encrypted controls, with one immutable
   request fingerprint, and sender approval only after that commit response.

2. **Revision rejection is not durable quarantine.** Kotlin
   `GroupsCrypto.kt:87-92`, Swift `GroupsCrypto.swift:130-137` throw from the
   transaction when revision/bootstrap is missing. Signal decryption, payload,
   fingerprint and receipt all roll back. A valid message arriving before its
   first approval can expire without ever reaching local durable recovery.
   Required: authenticated holds commit together with Signal state, context
   fingerprint and receipt; future revisions auto-reprocess after controls;
   old revisions remain visibly withheld and offer explicit resend recovery.

3. **Concurrent joined people cannot be approved.** Kotlin
   `GroupsSession.kt:120-124`, Swift `GroupsSession.swift:165-171` require relay
   roster equals approved roster plus exactly one person. Two accepted
   invitations before approval prevent either approval. Required: serialize
   pending admission or authorize deterministic individual additions while the
   approved roster is a safe subset of the relay; sending remains paused until
   the exact final roster is approved.

4. **Control reissue and conflicting revisions lack reconciliation.** Kotlin
   `GroupsControlCrypto.kt:18-20,38-45,85-94`, Swift
   `GroupsControlCrypto.swift:28-30,56-66,130-146` reuse old bytes forever and
   require every recipient still reports accepted/delivered. Offline expiry or
   revocation therefore blocks local reconciliation. A fresh envelope carrying
   an already-applied transition under a new transport ID is queued as missing
   history. Required: separate original logical transition/revision from
   transport admission; exact equivalent reissues deduplicate against durable
   prior/result state; contradictory same-revision rosters freeze visibly.
   Concurrent admins approving the same joined person must also converge.

5. **Incoming data can create a first-use identity.** Kotlin
   `GroupsCrypto.kt:78-85`, Swift `GroupsCrypto.swift:119-125` permit an absent
   peer-device route and do not require an existing identity pin before
   decrypting data. An account ID in an approved roster alone does not bind an
   unknown Signal identity to that account. Controls already demand a pin.
   Required: hold unknown/changed member identities for explicit review and
   preserve identity continuity before normal rendering. Authentication of
   first-use account keys needs the stated fingerprint/admin-binding policy;
   do not describe ordinary TOFU as an independently verified identity.

## Other material behavior

* Backend retry states include `unavailable` and `identity_changed`; Kotlin
  `GroupsCrypto.kt:61` / Swift `GroupsCrypto.swift:91` reject both as malformed
  responses instead of showing the real delivery outcome.
* Departed histories are stored, but Kotlin `GroupsSession.kt:35-36` / Swift
  `GroupsSession.swift:39-43` replace the visible list with active groups only.
  Provide an accessible local past-groups/history section after refresh/restart.
* Group mutation journal scopes are endpoint-specific, so a failed pending
  change can coexist with a rename/invite/other endpoint mutation that changes
  its epoch. Serialize membership intent per group and provide explicit
  pending/recovery states rather than allowing unrelated changes to strand it.
* First add control can arrive before join acceptance, after acceptance but
  before an active-list refresh, or before the first data message. Bootstrap
  must remain pending without approving recipients, retain the exact reviewed
  pinned sender/control, and reprocess held data only after explicit consent.
* Previously delivered messages remain valid local history after a sender
  leaves, blocks, changes identity or is deleted. New traffic from retired
  devices is held/rejected; replay of an already committed exact envelope is
  idempotent and does not become a new unread message.

## Ordering and recovery contract

Network mailbox order is untrusted. Equal server timestamps, clock changes,
multiple senders, pages and reordered controls cannot authorize content.

1. Persist immutable outgoing ciphertext and all Signal ratchets atomically;
   submit once; recover uncertain results with those exact bytes and IDs.
2. Commit a roster mutation and its control fanout in one server transaction.
   A rejected transaction exposes neither mutation nor new queued controls.
3. Validate each incoming envelope's account/device/group/kind/ID/time context
   and pre-existing Signal identity continuity. Unknown identity holds encrypted
   transport for review; malformed or conflicting contexts never become chat.
4. A successful authenticated decrypt commits its ratchet, exact replay
   fingerprint, receipt, and either a normal message or an encrypted local hold.
   Never throw away an otherwise valid decrypt only because an approval is late.
5. Current approved revision plus sender/self membership permits normal render.
   Higher revision/no bootstrap means `Waiting for group approval`; drain those
   holds after each valid contiguous control and explicit bootstrap. If the
   chain advances past a held revision, it becomes old-revision withheld.
6. Lower revision after a new approval means `Message withheld after the group
   changed`. Keep an explicit marker and recovery action. Do not render it by
   trusting sender time, relay acceptance time, a numeric sequence or old roster.
   Ask a still-current, identity-approved sender to resend as a NEW message ID
   under the latest revision. A removed sender cannot reauthorize it. Already
   delivered exact-envelope replays retain their original local history.
7. Receipt acknowledges durable local handling, not that content was displayed.
   A hold must survive app restart and relay's 72-hour body expiry. Surface
   missing-control history, identity review, expiry and orphaned-owner recovery;
   do not report all of them as a connection failure.

Without another authenticated causal fence, a receiver cannot distinguish a
legitimate queued older-revision ciphertext from a removed peer freshly
creating old-revision ciphertext. Transparent recovery would require additional
protocol machinery, for example a frozen, admin-authenticated per-recipient
manifest of exact pre-cutover ciphertext fingerprints, atomically bound to the
transition. IDs alone are insufficient because the removed sender could encrypt
a different payload under an old ID. This manifest protocol has not been
implemented or qualified; the explicit withheld/resend policy is the current
safe boundary, not a promise of lossless old-epoch delivery.

## Verification still required

Actual two-platform libsignal and vault crash/restart testing, real PostgreSQL
race tests, interrupted/expired controls, two joined people, duplicate/equivalent
admin controls, membership/rename races, device replacement during admission,
retired-device traffic, local past-group navigation and offline push/reconnect.
No production, Mac or phone action was taken for this review.

## Follow-up implementation status

The isolated backend now accepts mutation `control` atomically with role,
removal and leave. Exact ciphertext is bound in operation idempotency; losing
CAS/permission/queue checks roll back queued controls and membership together.
Retries retrieve committed admission even after closure or offline body expiry.
A targeted suite passed 53 tests with 5 PostgreSQL-dependent skips; this is
SQLite/API/domain evidence, not real row-lock or native runtime qualification.

The native owner is addressing the source findings in its separate worktree.
Those edits remain independently reviewable and unqualified until its actual
native compile, vault and libsignal tests run. Eight pure recovery-policy tests
in `backend/tests/test_group_recovery.py` exercise arrival ordering, bootstrap,
late revisions, identity holds, exact durable replay and explicit new-message
resend policy. They do not demonstrate native persistence.

Additional recovery limitation: pairwise authenticated control evidence is not
transferable to a different admin. Only its original actor can reissue it as the
same actor. If that account has left/deleted or its old device identity is gone,
current-member `/controls` admission and identity continuity may prevent reissue.
Expose verified recovery/recreation when the proof cannot be recovered; do not
promise that any current admin can resend every prior approval. Longer encrypted
control retention or transferable membership proofs would be separate reviewed
protocol changes. The current old-revision withheld/resend behavior remains an
unresolved offline UX/security tradeoff before enablement.
