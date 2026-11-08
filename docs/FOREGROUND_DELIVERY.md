# Foreground message arrival

An open conversation must receive messages when notification permission is
denied. `wss://api.mambovipi.app/v1/events` therefore carries one contentless
signal, `{"event":"inbox_changed"}`. The native app responds by running its
ordinary authenticated pending-message and delivery-receipt synchronization.
Ciphertext, message text, peer names and encryption keys never travel through
this socket. Receipt updates also wake the sender's active connection.

The handshake uses the same Bearer, `X-Vipi-Device-ID` and
`X-Vipi-Device-Secret` headers as the HTTPS inbox. No credentials appear in a
URL. WorkOS identity, the staging allowlist, active device and unrestricted
profile are checked before any signal and again at most every 25 seconds.
Receiving already-accepted messages is not gated on buying a new subscription.
Expired/invalid identity closes with 4401; replaced devices or restricted accounts
close with 4403. Temporary unavailability closes with 1013. Clients refresh expired
tokens, apply bounded reconnect backoff, and stop on background/account change.

Each API worker has one PostgreSQL LISTEN connection. Delivery and receipt
transactions call `pg_notify` with an opaque device ID; PostgreSQL publishes only
after commit. Independent workers receive the same signal, and only the worker
with that device's active socket forwards it. No per-message external queue or
new network service is introduced. Socket queues coalesce to one signal. Every
connection starts with a catch-up signal; missed notifications and reconnects
therefore cannot replace or lose the durable HTTPS delivery journal. Losing the
database listener closes affected sockets and reconnects with bounded backoff.

Uvicorn's pinned Sans-I/O WebSocket adapter sends protocol pings every 20 seconds,
requires a pong within 20 seconds, disables compression and caps incoming messages
at 512 bytes. Application text/binary input is rejected; this is not a second chat
transport. Nginx forwards the Upgrade headers on the existing HTTPS origin.
Its 35-second upstream idle timeout is kept alive by protocol pings.

The starting bound is 200 foreground connections per worker, two API workers,
and at most two overlapping connections for one device. This leaves capacity
within the existing 500-connection-per-worker limit for ordinary HTTPS requests.
This is an initial resource bound, not a claim of million-user capacity. Raising
it requires measured memory, authentication/reconnect, database and latency
qualification. More workers/hosts can listen to the same PostgreSQL channel;
the notification layer itself is not durable storage or an independent message
broker.

Backend qualification includes real PostgreSQL cross-listener commit/rollback,
recipient and sender wakeups, identity/device denial and revalidation, bounded
queues, disconnect cleanup, reconnect catch-up and a real loopback WebSocket
handshake/ping/oversized-frame check. The live TLS proxy passed qualification on
November 7 at service revision `9337972`. Deployment waits for public handshake
convergence after nginx's asynchronous graceful reload; a successful reload
command alone does not mean every accepting worker has applied the new headers.
Both native apps subsequently passed hands-off foreground arrival through this
public endpoint with notification permission denied. The Android network-loss
run caught up after reconnect without navigation, refresh or app restart; both
directions have server delivery receipts and cleared ciphertext. Android's first
observed catch-up was 18.85 seconds after network restoration, including backoff.
This is a measured observation bound, not exact wire latency. Background delivery
still uses APNs/FCM and remains a separate actual-provider qualification gate.

`qa/backend/qualify_foreground_load.py` exercises two separate local workers and
real PostgreSQL with an isolated schema. The November 8 run completed 480
message/receipt exchanges over 192 open sockets in 7.47 seconds, with p95 accept
latency of 254.9 ms and roughly 107 MB peak RSS per worker. It uses synthetic
opaque envelopes, fixture authentication and loopback networking. Production
JWT/provider overhead, internet behavior, native encryption, background delivery
and sustained production capacity require separate evidence.
