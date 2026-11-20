# Foreground conversation events

This source adds optional typing and explicit read receipts to the existing
`/v1/events` WebSocket. It requires no database migration. Deployment is separate.
Old sockets still receive only `{"event":"inbox_changed"}`. Old delivery/status
APIs expose internally read messages as `delivered`.

An upgraded client opts in with `X-Vipi-Chat-Events: 1` on the authenticated
WebSocket handshake, alongside the existing bearer token and device headers.
No capability header, event, or URL is added to legacy responses. An older
server can return 404 for the new HTTP endpoints; clients should disable the
optional feature for that session rather than retry continuously.

## Typing

`POST /v1/conversations/{peer UUID}/typing` accepts `{"active":true}` or
`{"active":false}` and returns `{"accepted":true}`. It requires an authenticated,
active device, two available unblocked accounts, and a message relationship
between their current devices in the retained delivery ledger. A changed device
must establish its own encrypted conversation first. Once old delivery metadata
expires, sending a new message establishes the relationship again.

An opted-in recipient receives
`{"event":"typing","peer":"sender UUID","active":true}` (or false).
This is transient PostgreSQL NOTIFY metadata: no typing rows, message content,
notifications, or push jobs are created. Foreground clients should throttle
updates, send false on send/leave/background, and expire a remote indicator
locally when updates stop. The endpoint allows at most 60 requests per minute.

## Explicit visible-message receipts

`POST /v1/conversations/{peer UUID}/receipts` accepts
`{"seen":["incoming message UUID"],"check":["outgoing message UUID"]}`.
Each array is optional and bounded to 64 UUIDs. The response is
`{"acknowledged":["consumed seen UUID"],"read":["confirmed outgoing UUID"]}`.

`acknowledged` echoes the deduplicated supplied seen IDs, including unavailable,
expired, blocked, and foreign IDs. Such IDs are indistinguishable no-ops and
cause no message writes or routed events. Acknowledgement consumes a client's
local read outbox; it is not proof that an ID exists or was marked read.

Only a matching incoming message for this account, current recipient device,
and named peer can transition from accepted/delivered to read. Explicit seen
can race the ordinary delivery ACK: it clears accepted ciphertext and records
read directly. Repeating seen is idempotent. This endpoint should be called
only after plaintext is durably saved and actually visible in the conversation.

`read` contains only matching, confirmed read rows from `check`, scoped to the
requesting sender's current device and the named peer. Missing entries convey
no new status; clients must preserve already-confirmed read state. The endpoint
allows 240 requests per minute. Existing delivery-ledger retention still applies.

A sender's opted-in socket receives
`{"event":"receipts_changed","peer":"recipient UUID"}` when read state changes.
Clients should coalesce these hints and query visible outgoing message IDs.
Read hints do not contain message IDs or content. Ordinary accepted-message ACK
catch-up remains compatible with legacy inbox hints.

## Bounds and authorization

Each socket coalesces at most 32 event/peer hints; typing prefers dropping older
typing hints under pressure. Existing worker/per-device connection limits remain.
NOTIFY is emitted only on transaction commit and reaches other workers. Rollback
is silent. Structured hints revalidate the socket, current devices, blocks and
peer availability before delivery; typing also rechecks the message relationship.
There is no new push path, production action, or external send in this change.
