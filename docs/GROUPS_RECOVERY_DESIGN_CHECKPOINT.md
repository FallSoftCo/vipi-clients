Current implementation checkpoint: see [operation recovery wire](GROUPS_OPERATION_RECOVERY_WIRE.md). The dated design below records the original unimplemented handoff; native recovery/notification gaps remain explicit.

# Pending recovery/notification contract — source handoff

November 20 UTC. Root reprioritized the protocol owner to launch capacity before
implementation of this extension. **DESIGN ONLY**: none of the endpoints/tables
below exists at protocol commit `a0b6f83b`. Groups remains disabled. Existing
atomic membership control admission is implemented at `acd9f28d`; post-lock
principal/device revalidation is implemented at `1a5e4a9a`.

## Durable cancellation and admission receipt

A volatile `group_epoch_changed` or `group_recipients_changed` response does not
prove that another earlier timed-out submission cannot arrive later. Clients
must not discard their immutable pending journal based only on that response.

Agreed proposed endpoint:

`POST /v1/groups/{group_id}/operations/{request_id}/cancel`

Body: `{action,expected_epoch,original_device_id,target_id?,title?,role?,invite_id?,control?}`.
Actions: `rename`, `invite`, `accept`, `decline`, `cancel-invite`, `role`, `remove`,
`leave`, and `control`. The `control` value is the exact original immutable
fanout `{id,epoch,created_at,envelopes}`; for standalone action `control`, the URL
request ID equals that fanout's ID. `original_device_id` comes from the actual
DeviceCredential at original preparation, never roster metadata.

Under the same stable user/group locks as admission, resolve the exact original
operation fingerprint. If already committed:
`{status:"admitted",request_id,group_id,result:<saved original snapshot/left or control aggregate>}`.
Otherwise persist an exact request-bound cancellation tombstone, then return
`{status:"cancelled",request_id,group_id,expected_epoch}`. A late original must
check this tombstone under the same locks and fail `group_operation_cancelled`.
Wrong descriptor/request fingerprint stays 409 and frozen, not safe-to-discard.
Store original admitted outcome in operation receipt metadata so later removal
or roster changes cannot rewrite the original result or disclose a new roster.

Do not time-delete a mutation cancellation while its expected epoch could still
admit: mutations currently have no immutable request timestamp. Once group epoch
has advanced past that expected epoch, the old request is permanently stale;
closure/account deletion also prevents resurrection. Standalone control TTL
provides an additional immutable expiry fence. Only then may tombstone cleanup
rely on that monotonic rejection. Define retry and legacy-receipt behavior in the
migration; do not fabricate missing original outcomes.

After an authenticated `cancelled` receipt for the exact stored descriptor,
native UI explicitly reviews current people, archives the unsent operation and
ciphertext, and permits a NEW request/control/message ID with fresh encryption.
Never roll ratchets backward. Uncertain transport/JSON outcomes retain exact
original bytes. `admitted` reconciles the original intended transition instead.

## Private per-user group notification preference

Proposed `GET /groups/{id}/notifications` returns initial
`{muted:false,version:0,request_id:null}`. `PUT` body:
`{muted,expected_version,request_id}`; return `{muted,version,request_id}`.
Use CAS version progression and immutable current request identity so a delayed
old mute/unmute cannot undo a newer preference. Other members must not see it.
Native journals its pending request/version/value separately from latest desired
preference and shows pending until relay acknowledgement.

A group-aware push outbox must preserve muted contentless inbox wakeups while
suppressing APNs alert/sound for that recipient's muted groups. Muted-only APNs
uses background/content-available with correct background headers; FCM remains
contentless and can carry suppress-alert status for its native dispatcher.
Unrelated direct or unmuted-group alerts must survive coalescing. Recheck mute
at dispatch, preserve generation races, device replacement and deletion cleanup.
Already dispatched notifications cannot be recalled. Existing one-to-one push
behavior must be preserved. Merely storing a local toggle is insufficient.

## Eligible recipients for control recovery

DATA stays strict: exactly every current non-sender member has a single active,
unrestricted, unblocked device, or admission fails.

CONTROL fanout must permit exactly CURRENT eligible non-sender routes (active,
non-suspended/non-deleted/unblocked accounts with a single active device).
Inactive/suspended/blocked accounts are omitted; snapshot `device_id=null`
communicates control-ineligible routes. This enables atomic remove/leave even if
its departing target has no usable device. Fail closed on multiple active
identities. Optional pending invitee still requires valid invite/admin authority.

For already-server-departed users (block/delete/restriction), the client may
explicitly author an authenticated REMOVE/LEAVE reconciliation against its
approved prior roster, using current eligible server routes. It must validate
the exact intentional delta independently; a strict prior superset is not
permission to accept arbitrary server additions or silent owner succession.
Original-owner disappearance can still require verified recreation. This needs
native approve-departure UX and authorization/retry tests, not just a relaxed
backend recipient count.

## Required implementation/qualification

The proposed extension needs migration, saved outcomes/tombstones, API models,
exact fingerprint helpers, account/device deletion cleanup, bounded storage and
PostgreSQL/SQLite race tests. Native implementation must match this wire and
retain Groups OFF until real compile, pinned Signal exchange, crash/retry,
notifications and offline UX qualification. No PostgreSQL/native/deployment
claim follows from this design checkpoint.
