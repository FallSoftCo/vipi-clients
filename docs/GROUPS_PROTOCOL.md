# Groups upgrade protocol v1 — isolated, disabled by default

This is a separately qualified upgrade. `VIPI_GROUPS_ENABLED=false` by default;
all `/v1/groups` routes return `groups_not_available` (404) until deliberately
enabled. It requires migration `20261119_02`; it does not change free one-to-one
admission. No billing, trial, vBot, or server translation participates.

See [required authenticated membership](GROUPS_MEMBERSHIP_AUTH.md); the native
approval chain and coordinator must be qualified before enablement.

## Security and privacy boundary

The relay knows group IDs, names, member IDs/roles, invitations, epochs, device
IDs, routing, message IDs, sizes and times. Names and rosters are **not** end to
end encrypted. Message bodies use the clients' existing pairwise libsignal
sessions. This is not Signal Private Groups, MLS or Sender Keys and does not
inherit those systems' group metadata privacy. The service cannot verify that
all recipients receive identical plaintext. Do not claim otherwise.

A sender first requires an authenticated approved roster matching the relay
roster, then encrypts a versioned JSON object for each recipient, using the same
existing Signal session machinery and identity-change confirmation as direct
chat. Plaintext object: `{ "version":2, "kind":"group", "id":"envelope UUID",
"sender":"account UUID", "recipient":"account UUID", "createdAt":<UTC Unix milliseconds>,
"text":"original text", "sender_device_id":"UUID", "group_id":"UUID",
"group_epoch":N, "group_revision":R, "group_message_id":"shared message UUID" }`.
Receiver MUST compare every envelope context field to transport metadata, and validates group_revision
against its authenticated membership history,
reject a mismatch or incomplete group metadata triple, deduplicate by `(group_id,group_message_id,sender)`, and never
render this object as a direct-chat message. Epoch is a roster/version fence,
not a cryptographic key rotation. Translation, mute/read/unread and persistence
are local per user. Identity-changed recipients require explicit confirmation,
new key claims and fresh encryption; never redirect old ciphertext.

Groups have at most 16 current members including their creator. An owner can
invite, rename, grant/revoke admin, transfer ownership, and remove others.
Admins can invite, rename and remove ordinary members. Members can leave.
An owner leaving/deleting transfers to the oldest admin, then oldest member
(stable user ID tie-break); a final departure closes the group. Removing or
leaving cancels undelivered group ciphertext addressed to the departed user.
It does not erase messages already delivered or another member's local copy.
Joining never backfills messages. History forwarding/screenshots cannot be
prevented. Blocking leaves all shared groups for the blocker, with that same
ownership transfer; unblock does not rejoin. UI must explain this consequence.

## Wire contract

Authentication and device headers are identical to current `/v1/messages`.
UUIDs are canonical strings. All dates are UTC ISO8601. Mutation bodies include
`request_id` for idempotency (create instead uses stable `id`); membership/name/
role/invitation mutations also include `expected_epoch`. Successful mutation
responses are a current group snapshot unless stated otherwise. A snapshot is:

```
{"id":"UUID","title":"Name","epoch":1,"state":"active",
 "members":[{"user_id":"UUID","username":"alice","display_name":"Alice",
              "role":"owner","joined_epoch":1,"device_id":"UUID or null"}],
 "invitations":[{"id":"UUID","user_id":"UUID","invited_by":"UUID",
                 "expires_at":"ISO8601","state":"pending"}]}
```

Only a current member sees a group snapshot. Device IDs are the current active
devices; claim bundles with the existing key endpoint before encryption.

* `GET /v1/groups` → `{groups:[snapshot], invitations:[{id,group_id,title,
  invited_by,expires_at,epoch}]}`. Invitations are only this user's pending,
  unexpired invitations; list refresh is the authoritative reconnect source.
* `POST /v1/groups` `{id,title}` → snapshot. Creates owner-only group epoch 1;
  repeated same ID/creator/title is a safe retry; changed content conflicts.
* `GET /v1/groups/{id}` → snapshot.
* `PATCH /v1/groups/{id}` `{request_id,expected_epoch,title}` → snapshot.
* `POST /v1/groups/{id}/invitations`
  `{request_id,expected_epoch,user_id}` → snapshot. `request_id` is invitation
  ID. Explicit account-bound consent; no public link or silent add. Expires 7d.
* `POST /v1/groups/{id}/invitations/{invite_id}/accept`
  `{request_id,expected_epoch}` → snapshot. Existing members must be unblocked
  in both directions; cap and current epoch revalidated atomically.
* `POST /v1/groups/{id}/invitations/{invite_id}/decline`
  `{request_id,expected_epoch}` → `{declined:true}`.
* `DELETE /v1/groups/{id}/invitations/{invite_id}`
  `{request_id,expected_epoch}` → snapshot (admin cancel).
* `PATCH /v1/groups/{id}/members/{user_id}`
  `{request_id,expected_epoch,role:"member"|"admin"|"owner"}` → snapshot.
  Owner only; `owner` transfers ownership and demotes old owner to admin.
* `DELETE /v1/groups/{id}/members/{user_id}`
  `{request_id,expected_epoch}` → snapshot. Cannot remove self; use leave.
* `POST /v1/groups/{id}/leave` `{request_id,expected_epoch}` → `{left:true}`.
* `POST /v1/groups/{id}/messages`
  `{id,epoch,created_at,envelopes:[{id,recipient_id,recipient_device_id,
  cipher_type:2|3,ciphertext:"base64"}]}` →
  `{id,group_id,epoch,deliveries:[{id,state,expires_at}]}`.
  Exactly one envelope per current active non-sender device, no omissions or
  extras; every member needs an active device. Admission is transactional across
  all envelopes. Preserve exact request/encrypted bytes and IDs for retry. Do
  not advance Signal encryption state again on HTTP retry. A request may total
  at most 1.5 MB (each ciphertext at most 65536 decoded bytes).

Every user-driven snapshot-changing successful mutation advances the epoch once,
including pending invite changes. Automatic invitation expiry/cancellation does
not reserve or change membership. Retries retain original admission identity; they return
the current snapshot and never repeat a mutation. A conflicting request ID is
409 `group_request_conflict`; outdated epochs are 409 `group_epoch_changed`.
Reload, show the changed roster, and ask the user to resend freshly encrypted
content after necessary identity review. New IDs are not a bypass for epoch
checks. Concurrent create/member/cap admissions serialize under user/group row
locks in PostgreSQL. Group fanout is not a loop of independent HTTP sends.

Existing pending inbox items add nullable `group_id`, `group_epoch`,
`group_message_id`, `group_kind`; direct items omit them. A group's individual envelope IDs use
existing `/v1/messages/{id}/receipt` and status endpoints. Sender aggregate retry
returns per-device delivery status; no group-wide read receipt is implied.
Opaque messages expire after 72 hours with existing inbox expiry. Membership
and message acceptance order are serialized. An acceptance committed before a
leave may already have reached a client; departure cancels queued copies.
Stale/inactive sender devices cannot send or retry. A new device has no old
history and does not inherit old-device ciphertext. Native clients must persist
outbound encrypted fanout atomically before submitting it, and resume it without
re-encrypting after reconnect.

Reports reuse `/v1/reports` and the selected **individual envelope ID**, original
sender and explicit selected text with `report-v1` consent. The relay does not
fetch or decrypt chat history. Account deletion removes membership/invitations,
purges its queued messages and erases its operation/message retry metadata;
remaining members retain their group and already delivered messages.

## Qualification boundary

SQLite unit/integration tests exercise authorization, exact fanout, retries,
expiry, queue rollback, blocked joins, deletion and revocation. PostgreSQL row
lock/race qualification, actual iOS↔Android libsignal exchange, native persistence
crash/restart, identity confirmation UX, report UI, push/reconnect and rollout
remain release gates. Passing opaque-byte relay tests is not encryption proof.

## Atomic membership/control mutation extension

Role changes, removal and leave can include `control` in the mutation body:
`{request_id,expected_epoch,...,control:{id,epoch,created_at,envelopes:[...]}}`.
That control is an immutable pre-mutation CURRENT roster fanout, with
`control.epoch == expected_epoch`. Admission and mutation share one savepoint
and outer transaction; rejection of either leaves neither effect. Do not send
that control separately first. The sender applies its own intended authenticated
transition only after the atomic response, comparing the returned roster with
that intent, never approving arbitrary returned additions.

Snapshot responses (or `{left:true}`) add `control_acceptance` with the usual
`{id,group_id,epoch,admitted:true,deliveries}` result. Exact mutation retry binds
the complete original encrypted fanout in the operation fingerprint. It retrieves
original admission after leave/closure or per-recipient offline expiry; it does
not re-encrypt, reapply membership, or resurrect a ciphertext. `admitted:true`
means the fanout transaction was accepted; `delivered`, `expired`, `unavailable`
or `identity_changed` are separate per-device outcomes. A recipient removed by
that same mutation has its queued copy cancelled. The sender's locally known
transition still committed and remaining clients may need a fresh authenticated
reissue. Control admission metadata is retained for the mutation's 30-day retry
window; body retention remains 72 hours.

Standalone `/controls` remains for post-join approval and control-history
reissue; it also returns `admitted:true`. A control previously admitted separately
cannot be retroactively attached to a new atomic mutation (`409
group_control_already_admitted`). Unsupported atomic control actions are rejected.
A definitive rejection permits explicit recovery; an uncertain network result
requires retrying the saved mutation/control bytes before creating new IDs.

The old-revision withheld/resend policy in [the independent review](GROUPS_REVIEW_20261119.md)
is an unresolved offline UX/security tradeoff requiring review before release.
It must not be described as seamless, lossless offline group delivery.
