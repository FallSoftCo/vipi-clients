# Small encrypted groups qualification

The upgrade integrates protocol `dc23044f` and clients `d514886a` on the
one-to-one baseline `b4cdf986`. Release builds keep groups disabled. Android
qualification uses `-PvipiGroupsQualification=true` and, for the journey
fixture, `-PvipiSourceContextQualification=true`. Its package is
`co.fallsoft.vipi.groupsqa`. The iOS opt-in requires a simulator and the
`VIPI_GROUPS_QUALIFICATION` compilation condition.

## What people can do

Open Chats → New chat → Groups, name a group, choose existing people and
invite them. Pending invitees appear separately. Invitations require
acceptance and admission to the authenticated roster. A group supports up to
16 people including its creator, with one active device per member. Members
send encrypted text and see its sender. The relay sees titles, membership,
roles and routing metadata.

Both conversation screens use the account's existing immersion renderer and
language settings. Shallow and Deep, reveal-original, tap-to-listen and
Autoplay are available through the same translation and speech owners as a
direct conversation. An offline Android run used two independently keyed
synthetic accounts and the production group receive path. Maya’s English
text opened in Shallow, then switched to a Spanish Deep translation. Holding
showed the English original. Tapping submitted the entire Spanish sentence
to the local voice in one render, played 5.046 seconds through AudioTrack
and highlighted 15 word ranges in the native paragraph. The muted emulator
did not test acoustic quality. iOS group translation and speech still need
runtime qualification. [Screens and native audio](https://system76-pc.tailb77f2a.ts.net/8bar/vipi-studio-20261120/#groups-spanish-immersion-android-20261121-r01)

Group APNs wakeups omit direct-message preview tickets. The direct preview
route rejects a ratchet chain containing group text or group controls, including
when a newer direct message follows a group message. Group traffic alone
cannot establish direct typing or read-receipt eligibility. Local unread
state is supported. Per-group alert suppression, delivery to physical devices
and remote per-member seen indicators remain unqualified. Mute is hidden.

## Evidence on the integrated source

| Surface | Observed result |
| --- | --- |
| Backend | 139 passing PostgreSQL-backed tests across group behavior, schema migrations, push, events and chat boundaries. The disposable database used a local Unix socket and was shut down. The canonical aliases revision remains `20261119_02`, followed by group revisions `20261121_01` and `20261121_02`. Old isolated prototypes reused the alias revision ID and require separate reconciliation before migrating any retained prototype database. |
| Android native crypto and routing | 10 instrumentation tests passed. One created 16 separate account vaults on one emulator. The creator established 15 pairwise Signal sessions, each account reached the same authenticated roster, and 15 recipients independently decrypted the creator's group text. A three-member test exercised offline delivery, reopen, duplicate handling and removal. |
| Android normal entry | One separate instrumentation journey passed. Using a synthetic service fixture and the actual activity, vault and groups coordinator, it selected Maya, checked “2 of 16,” created Saturday practice, sent one invitation, switched immersion mode twice and opened group info. Maya remained pending. [Reviewed native screens](https://system76-pc.tailb77f2a.ts.net/8bar/vipi-studio-20261120/#groups-create-invite-android-20261121-r01) |
| Apple | The unsigned opt-in simulator application and notification extension compiled. The existing test target references the removed `BundledImmersionCatalog` in `SwahiliConversationCoverageTests.swift` and did not build. The current iOS group screen and push behavior still need runtime qualification. |
| Earlier cross-platform evidence | The earlier client branch connected three synthetic native accounts on Android and iOS to the local authenticated PostgreSQL relay. Eight stages completed, 17 envelopes were delivered and four logical user messages had zero duplicates. The integrated source has yet to repeat this mixed-platform run. |

The New chat entry follows the compose-to-group path in the inspected
[XChat creating-a-group flow](https://mobbin.com/flows/3c481bf6-0865-47a9-9cc9-c5bf6025bfe4).
The group conversation reuses Vipi's established immersion controls.

## Rollout decision

Keep the feature on its upgrade branch. Before release, exercise actual
mixed-platform join, send, leave, device replacement and recovery after
missing controls on the integrated source. Verify both clients' localized
screens, translated speech, background delivery and user-visible receipt
semantics. The 16-account run established one creator's encrypted fanout
and recipient agreement on one emulator. It did not measure 16 physical
devices, all-to-all throughput or public service capacity.
