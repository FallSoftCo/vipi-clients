# Required authenticated membership layer

Status: executable reference and native integration contract. This is required
before Groups enablement, alongside actual two-platform libsignal QA. Relay
membership is never the source of encryption authority.

Signal's [Sesame specification](https://signal.org/docs/specifications/sesame/)
describes authenticated device sessions and adversarial mailboxes. It explicitly
requires identity authentication; it does not supply this application's group
membership state machine. Signal's [Private Groups design](https://signal.org/blog/signal-private-group-system/)
is a different protocol, with different metadata properties. The following is
application authorization carried inside existing libsignal authenticated
messages; no new signature, cipher, key agreement or MAC is added. It still
requires security review and does not claim Private Groups or MLS properties.

## Trust and durable state

Each device stores `ApprovedGroupRoster` separately from untrusted
`GroupSnapshot`. A server-only name, role, invitation, membership, device route
or epoch change MUST NOT approve an encryption recipient. Creator seeds only
its own owner-only roster, revision 1. New members explicitly accept a trust
anchor from a previously pinned inviter/admin Signal identity: the authenticated
control must name this exact group and include that user as the newly added
member. An HTTP invitation cannot establish that anchor. Do not silently pin a
new admin identity and call that a validated chain. A changed identity halts
control processing and sending until the existing explicit identity review.

A revision is a local authenticated-roster counter independent of server epoch.
Every roster control increments it by exactly one, with an exact full previous
roster match. Name/invite changes can change server epoch without changing the
approved membership. Preserve past approved revisions for audit and already delivered deduplication;
fresh sends and newly received text use only the latest approved revision. DATA
plaintext adds positive integer `group_revision`; recipients validate sender and
recipient membership in that latest authenticated revision. Newly arriving older
revision messages are quarantined, even if they were legitimately queued before
a removal. Untrusted relay timestamps cannot distinguish those messages from a
removed peer freshly encrypting against historical membership. Exact envelopes
already committed locally remain harmless idempotent replays. The decrypted revision
cannot be supplied by the relay. The sender checks the current relay roster's
exact `{user_id,role}` set equals its approved roster before encrypting.

## Control transport and plaintext

`POST /v1/groups/{id}/controls` uses the same encrypted fanout body as `/messages`,
plus optional `invited_user_id`. It targets exactly the CURRENT member devices
except sender, plus that one pending unexpired invited account when supplied.
Only owner/admin may target an invitee. A current member can transport controls
because a member may authenticate its own departure; native authorization of
the decrypted operation is mandatory. The relay cannot inspect this content.

Pending envelope metadata adds `group_kind:"control"|"message"`. Reject incomplete
or unknown group metadata; a control must never fall through to a text view.
Control IDs and per-device envelope IDs are independent stable UUIDs. Control
ciphertext and Signal ratchet state are committed atomically before submission;
HTTP retries reuse those bytes. The usual v2 envelope context fields remain,
with `kind:"group-control"` and these top-level fields replacing text:

```
{"actor_id":"account UUID",
 "from_revision":1,"to_revision":2,"server_epoch":4,"action":"add","target_id":"account UUID",
 "previous_members":[{"user_id":"owner UUID","role":"owner"}],
 "members":[{"user_id":"owner UUID","role":"owner"},
            {"user_id":"new member UUID","role":"member"}]}
```

The usual outer `id` is the individual envelope ID; `group_message_id` is the
shared logical control ID. The actor equals the
Signal-authenticated sender, already pinned before decryption. Group ID and
normal envelope context match the outer authenticated payload. Array order is
irrelevant; duplicate members, extra roster fields, invalid roles, >16 members,
noninteger revisions and multiple/no owners are invalid (a final leave can
produce an empty roster). Store both control and approved roster in the same
vault transaction that commits Signal decryption and deduplication. Repeated
identical control is idempotent; a different control at the same revision is a
conflict. Unknown/skipped revisions are queued, never replaced by relay state.

Action rules (actor authority is evaluated against the previous approved roster):

* `add`: owner/admin adds exactly target as ordinary member; no other changes.
* `remove`: owner can remove another nonowner; admin only another ordinary member.
* `role`: owner grants/revokes admin for another nonowner; `role` is admin/member.
* `transfer`: owner makes another existing member owner and itself admin.
* `leave`: actor removes itself. Owner with other members MUST explicitly transfer
  first. A final owner leave closes the group.

`backend/vipi/group_approval.py` is an executable reference, not server-side
proof of control authenticity. Native validators must pass the same negative
cases. A caller asserting `identity_pinned=true` is not a substitute for the
real libsignal identity-store check.

## Coordinator obligations

Owner/admin operations persist the exact intended roster delta independently
of the server response. Generate controls only for that intended delta; never
approve an arbitrary returned roster. Owner transfer, role/removal changes and voluntary departure use the atomic
mutation `control` field: prepare encryption for the current roster before
submission, then submit control and mutation together. Never admit the control
through a separate request before the mutation. Once pending, stop text sends
until the atomic mutation and approvals reconcile. A failed/uncertain mutation keeps that operation pending for exact
retry; it does not silently roll back or approve a different roster.

An invitee's server acceptance does not authorize anybody to encrypt to it.
After acceptance, an existing approved admin explicitly approves that intended
join and emits the `add` control to the whole new roster. The invitee reviews its
pinned admin trust anchor; existing members validate the previous roster chain.
This can temporarily freeze sending while the approval is incomplete.

Blocking/deletion/server suspension immediately deny routing and remove relay
membership, but cannot forge a departing peer's control. A remaining approved
owner/admin can explicitly authorize a valid removal and send the corresponding
control. Silent server owner succession is not cryptographic authority. If the
old owner disappeared without a prior transfer, the current group remains
frozen: recreate a new group with explicit verified identities. A replacement
phone likewise cannot inherit approved group authority or old ciphertext from
the relay. Recover a durable authenticated local chain or establish a new,
explicitly verified anchor; never reconstruct trust from HTTP roster fields.

Controls expire from relay after 72h. Original devices retain their authenticated
control history locally to reissue missing chains through fresh pairwise
sessions after identity review. Reissued controls carry original revisions and
transitions inside new envelope IDs; receipt retry and logical-control dedup
must remain separate. Missing history is a visible recover/recreate state.

A malicious server can suppress/fork delivery and observe group metadata. A
device that has not received a revocation can still hold an older approved
roster; authenticated control delivery is required for it to learn that change.
Honest-relay epoch fences reject stale fanouts while it reconnects. This is not
a proof that every offline device has learned a global revocation.
Pairwise delivery alone does not prove every participant received the same
plaintext or every control. An authorized malicious admin can add a member, and
recipients can disclose content. Do not promise total ordering, global
non-equivocation or retrospective erasure.
