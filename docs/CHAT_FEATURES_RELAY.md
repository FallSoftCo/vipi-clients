# Negotiating encrypted chat actions

Quoted replies and link previews travel inside normal direct and group ciphertext. Older clients can continue to display the ordinary message text. Reactions use a separate encrypted envelope because they do not create a visible transcript message. The only extra information the relay records for that envelope is the required protocol integer. The target, emoji, quote, URL and preview remain encrypted.

## Client contract

| Operation | Contract |
|---|---|
| Advertise | With the registered device’s usual bearer, device ID and secret, PUT `/v1/devices/chat-features` with `{"version":1}`. A successful response contains the effective `version` and that `device_id`. Renew on an active session within seven days. Version 0 immediately revokes support. An older server may return 404. |
| Direct readiness | Authenticated GET `/v1/people/{user_id}/chat-features` returns `version` and the active `device_id` (null for no active device). Compare the ID to the encrypted recipient. Existing block, deletion and suspension rules apply. |
| Group readiness | Read the current group details under the regular group protocol. The active roster members have `chat_features_version` and `device_id`. An absent version means 0. Refresh the current epoch and every active route before sending. Historical mutation receipts cannot certify a current lease. |
| Send | Add `"required_chat_features_version": 1` to a direct message or the top-level group message fanout. Keep existing encrypted envelope and idempotency IDs. Unsupported recipients or sender return HTTP 409 `chat_features_unavailable`. Device replacement, membership and epoch changes use the existing conflict errors. Omit the field for all existing traffic, including ordinary quoted replies and link previews. Group control routes reject it. |
| Receive | Send `X-Vipi-Chat-Features: 1` on all capable reads of `GET /v1/messages/pending`. Keep `X-Vipi-Group-Protocol: 1` for groups. Receivers acknowledge normally after a successful vault transaction. A legacy inbox read hides silent events and revokes the cached support lease for that installation. Previously accepted events remain available to a capable reader through normal message expiry. |
| Closed writer | With `VIPI_CHAT_FEATURES_ENABLED=false` (default), the service returns version 0 and rejects new silent admissions. Existing accepted events keep their immutable retry result. A capable recipient can still fetch and acknowledge them. |

The relay takes existing user and group locks before checking active devices and leases. The group accepts all intended envelopes together. A retransmission with an unchanged ID, ciphertext and capability requirement reads the original admission outcome. Switching an accepted ID between ordinary and silent delivery is a conflict.

Silent events notify connected clients over the existing WebSocket. They do not enqueue a visible APNs or FCM alert. Late push registration and background queue processing choose ordinary envelopes. An ordinary encrypted preview whose preceding Signal chain contains a pending silent event falls back to generic notification handling. The full app can process that chain through the ordinary inbox. A previously scheduled alert for a separate membership change keeps its existing behavior.

The relay limits unacknowledged silent events to 64 per exact sender/recipient device pair within a seven-day lease, including expired events. The shared recipient lock makes that bound apply to concurrent direct and group sends. A full backlog returns HTTP 429 `chat_features_backlog_full`. Keep the same immutable journal entry for a retry and keep text sendable. The group layer uses pairwise Signal sessions, so direct and group paths share this budget. The sender should check support before generating a new event. Never spin on a failed admission or encrypt new duplicates as retries.

## Deployment boundary

Revision `20261126_01` follows `20261121_04`. Its two additive columns are a nullable device capability expiry and a zero-default envelope requirement. Earlier rows are ordinary messages or unsupported devices without backfill. The service’s production readiness expects the new head. The existing B1/B2/B3 candidate seals predate this change. Coordinate a new migration and readiness transition separately.

First public admission requires compatible inbox and push selection on all serving/worker routes, including any retained generation that can fetch pending envelopes. First verify the new schema, old-client reads, group/peer capability lookup, push custody and both clients’ foreground delivery. Keep the switch off during mixed server generations. After admission, retain a version-aware reader and push consumer even when new admissions are closed. Database downgrade refuses while marked envelope rows remain.
