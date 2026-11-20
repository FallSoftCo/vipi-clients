# Exact operation recovery — disabled Groups upgrade

The isolated relay now implements `POST /v1/groups/{group_id}/operations/{request_id}/cancel`. It takes the checkpoint's original action, expected_epoch, original_device_id and exact original optional target_id/title/role/invite_id/control fields. Current principal/device authentication and post-lock revalidation remain required. Control ciphertext is opaque; its exact original fanout fingerprint is part of the operation identity.

A known exact admission returns `status: admitted` and its saved ORIGINAL result. No current roster is substituted. A previously admitted legacy receipt with no saved original outcome returns409 `group_operation_outcome_unavailable`; native clients must preserve their immutable pending journal and review rather than infer safe cancellation.

Otherwise the same user/group locks serialize an actor/request-bound cancellation tombstone against admission. Success returns `status: cancelled` with request_id/group_id/expected_epoch. A delayed original is rejected as `group_operation_cancelled`; altered descriptors, device context or ciphertext remain409 conflicts. Another actor cannot reserve or cancel the prepared operation's namespace.

Current/future-epoch mutation tombstones have no time TTL. Cleanup requires a monotonically advanced group epoch, closed group/account removal, or the immutable72h expiry of standalone control. There are at most256 outstanding tombstones per actor/group; current-epoch exhaustion returns429 and never silently forgets an earlier fence. Original admission snapshots expire with the existing30-day receipt fence; mutations advance epoch and cannot then resurrect. Account deletion removes its original outcome and cancellation metadata.

This is an upgrade-only migration from the existing isolated Groups schema. It must be reconciled with launch's alias migration before any integration/deployment; no branch migration is to be cherry-picked blindly. Groups is OFF by default and no production change follows.

First checks: existing isolated baseline63 SQLite tests passed at281dc28f; recovery plus related HTTP/atomic relay set36 passed. These are opaque transport/service tests, NOT real Signal/native qualification or PostgreSQL race evidence. Real PostgreSQL migration/races, cancellation endpoint HTTP edge cases, control eligible-recipient recovery, native pending-journal reconciliation and16-member offline end-to-end acceptance are outstanding in this checkpoint.
