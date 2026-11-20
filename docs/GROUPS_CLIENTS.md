# Groups native upgrade — source checkpoint

This branch is isolated from the free one-to-one launch. `GroupsUpgrade.enabled`
is false on both platforms and neither launch home calls the new group entry
point. Do not enable it based on source checks or relay tests.

## Implemented source

Both platforms have separate group models, encrypted account-vault storage,
contract HTTP adapter, pairwise Signal message fanout, authenticated roster
history, control fanout/decryption/bootstrap, durable immutable member mutation
plans, native coordinators and native screens. Create/select/name/invite flows
include the creator in the limit of16. Invites require acceptance. Group info
covers admin roles, ownership transfer, removal, leave, invitation cancellation,
local mute and unread state. Conversation rows attribute the sender and call the
existing immersion renderer with stable `group:<group UUID>:<logical UUID>` IDs,
original text and the current user's existing translation/audio owners. No bot,
subscription or payment API is introduced.

A relay snapshot cannot authorize a recipient. Creator-only genesis is seeded
from the known local create intent. All other membership changes require a
pinned existing Signal identity, exact previous roster/revision and a valid
single-member/role delta. Role/remove/leave submit the intended encrypted control
and exact roster mutation in one atomic HTTP request. Own approval advances only
after that request returns its durable admission receipt. That receipt is relay
transaction status, not cryptographic membership proof; the locally authored
control remains the intended authority. A retry can return a later relay snapshot;
that does not strand an already committed immutable operation. Fresh sends still
require the relay proposal to match the latest authenticated roster exactly.
Fresh text uses only the latest authenticated revision.
A server roster mismatch or pending mutation freezes sends. First-join trust is
an explicit confirmation of the decrypted full roster and pinned inviter.
Newly arriving old-revision text is withheld after a removal; exact already
committed envelope replay remains idempotent. Unknown/changed identities hold
immutable ciphertext until explicit encryption review. Pinned decrypted text
whose revision is not approved commits Signal state, secure withheld content,
context fingerprint and receipt together; it never enters normal text,
translation, autoplay or unread until authorized. Future-revision text can
promote after approval. Earlier-revision text offers a clear ask-to-resend draft.
Withheld placeholders cannot consume unread state; promotion re-evaluates only
visible, opened incoming messages. Pending controls retain their authenticated
sender device and must still match an unblocked, unretired pinned route before
bootstrap or deferred application. Invalid deferred approvals keep only a bounded
per-group rejection notice with an explicit dismissal; their recovery reservation
is released. Explicit bootstrap also stores its reviewed prior roster as an
historical anchor so equivalent fresh-transport reissue can be recognized.
Recovery admission is bounded to1024 records/32MiB per account and128/8MiB per
group using actual encoded sizes; existing holds are never silently evicted.
Held first-seen time preserves originally timely recovery after relay expiry.
Decrypted quarantine retains the exact authenticated sender key/device proof and
rechecks current unblocked/unretired continuity before promotion. A fresh
ciphertext cannot downgrade already displayed immutable logical history. Missing controls are retained and
valid consecutive controls drain atomically. Equivalent historical controls can
be recognized without rewinding the roster, and conflicting authenticated rosters
freeze fresh data. A returning control ID with altered content conflicts. Local owner departure requires prior ownership transfer;
automatic relay succession is not accepted as cryptographic authority.

The relay can see names, rosters, roles, invitations and routing metadata. This
is application membership authorization over pairwise Signal, not Signal Private
Groups or MLS. Suppression, availability forks, malicious authorized admins and
recipient disclosure remain outside the guarantees described here.

## References actually consulted

Mobbin MCP returned native creating-group flows whose inline previews were
inspected: [X](https://mobbin.com/flows/7dbf78a0-9a50-44d6-ae65-a15507f3db5c)
and [Fanatics Live](https://mobbin.com/flows/3a8c6203-883f-4801-b70c-0abf7092d5bd).
The member picker keeps clear selected state, name and handle; the conversation
keeps sender attribution. These are reference principles, not copied screens.

Built for Mars MCP exact article [Group Sessions](https://builtformars.com/case-studies/how-group-sessions-on-spotify-work)
informed explicit role/consequence context and recognizable names.
[Intentional Friction](https://builtformars.com/ux-glossary/intentional-friction)
informed targeted confirmations for removal, leaving, ownership and trust.
These sources have not validated this implementation's actual native UX.
A later BFM MCP written-flow critique reinforced specific pending actions,
visible join state and contextual recovery. Its example ownership and receiver
resend wording conflicted with this contract and was not adopted literally.

## Validation so far

- `git diff --cached --check`: passed for the source checkpoint.
- Shared pure protocol reference:22 authorization cases passed against the copied
  fixture. This runs the protocol owner's Python reference, not the native code.
- Fixture SHA256: `25c7dead55d9dd88956bebaeac321c39d6735e395a613d867ff08a7b52aeb2d3`.
- Native Swift and Android tests authored for those same22 cases, creator-inclusive
  selection and relay-only membership changes. Routing tests cover partial and
  unknown metadata. Three additional iOS sources exercise genuine pairwise
  control/bootstrap/text, all-recipient ratchet rollback, and delayed identity
  hold/promotion continuity. None of these native tests have run.
- No SDK/dependency install, native build, simulator, emulator, phone, iPad,
  desktop interaction, auth mutation, release build or production action performed.

## Integration and qualification still required

1. Merge only the separate upgrade with the frozen free incremental-word facade.
   Both source bases here predate that facade. Do not take old launch files from
   this branch as authority. The new UI supplies the current account's existing
   `ConversationImmersion` / `ConversationTranslation` and audio owner unchanged.
2. A separate dormant integration commit now wires native ChatSession to a
   GroupsSession sharing its exact account vault, core, account-auth transport
   and peer review state. It dispatches all four group metadata fields before
   direct receive, rejects partial/unknown group contexts, commits group receipts,
   refreshes/retries on the existing reconnect cycle, warms/replays namespaced
   immersion IDs through the same local owner, and closes GroupsSession before
   its vault. It also retains server-visible sender labels across departures.
   These source hooks have not been compiled or exercised. Merge their hunks
   into the frozen free facade; never overwrite current ChatSession with this
   branch's older base. No launch navigation activates Groups. Native group
   entry must be keyed to the account and supplied its existing local immersion
   and audio owner. Routing-negative native tests were authored, not run.
   Mute still requires actual notification delivery policy: current relay APNs
   uses a generic alert, so storing a native mute preference cannot suppress it.
   A real per-user relay mute policy or qualified extension/silent-local design
   is required before the UI promise is enabled. This is substantive missing
   behavior, not just a callback hookup.
3. Build/typecheck against retained native dependency closures in a root-allocated
   isolated Mac directory. New source uses existing libsignal Swift0.105.0 calls,
   Swift6 Observation, iOS18 scroll visibility and existing immersion signatures.
   Android uses current lifecycle-compose `LocalLifecycleOwner`, Compose Material3
   and the existing libsignal SessionCipher constructor. No native compiler has
   confirmed these assumptions yet.
4. Exercise iOS↔Android text and controls with real pinned identities, max16 people,
   malformed metadata, all envelope/context substitutions, ratchet rollback on a
   recipient failure, crash after encryption/before HTTP and after uncertain HTTP,
   pending immutable mutation retry, approval ordering/missing/reissued controls,
   concurrent admin mutations and identity/device replacement. Backend tests do
   not establish these native properties.
5. Complete expired-control/missing-chain reissue and verified-recovery UI,
   definitive no-admission mutation conflict recovery, selected-envelope reporting,
   and actual notification/unread integration. Durable pending-change and join
   plans now have Resume controls; pending create reopens its immutable name.
   Departed groups retain a read-only Past groups route across restart. Multiple
   accepted joiners can be approved one at a time while sends stay frozen until
   the full approved roster matches. Concurrent contradictory admin approvals
   freeze visibly; resolving that fork/recreating safely needs real qualification.
   First-use member identity binding remains an explicit security review gate.
   Control delivery and membership reconciliation when a member has no active
   device, is suspended, or was already removed by block/deletion also needs an
   explicit protocol/UI path; ordinary message admission remains fail closed.
   A departed/deleted/rekeyed original control author may be unable to resend an
   old pairwise proof; another admin cannot impersonate that proof. In that case
   offer explicit verified recovery or a new group, not endless retry. Current
   local stores enumerate group history, so long histories need paging/retention.
6. Perform real visual/accessibility validation at large font sizes, VoiceOver and
   TalkBack, narrow landscape, keyboard, RTL, long names, long messages, empty,
   loading, offline and destructive states. English copy is newly authored; full
   locale coverage remains a gate. Group conversation scroll following/history
   paging and autoplay controls still need parity with the qualified direct chat.

No world-class, production-ready, complete native UX or encryption qualification
claim follows from this checkpoint. The initial one-to-one launch stays separate.
