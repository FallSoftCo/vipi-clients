# Architecture

The November 18 owner decision is **full-message local translation through
existing on-device APIs only**. Apple Translation and Google ML Kit are the
current implementations. Apple API comparisons are retained research evidence,
not a shipping strategy change; the AICore probe has not run on a compatible
device. Do not add standalone model weights or inference runtimes. The
[current immersion decisions](DECISIONS.md#current-immersion-decisions--2026-11-18)
supersede the former catalog-based designs retained in Git history.

Deployment status is recorded in [DELIVERY_STATUS.md](DELIVERY_STATUS.md),
updated November 18, 2026. The designs below include dated qualification
notes; they do not supersede the current release receipts or authorize retired
hosts, devices, jobs or external actions.

## Components

| Concern | Choice | Qualification still required |
|---|---|---|
| iOS | Swift, SwiftUI, native concurrency and platform storage | Current OS text-size changes, physical runtime and release build |
| Android | Kotlin, Compose, coroutines, Room/SQLite, WorkManager | Current OS text-size changes, physical ARM64/16-KiB runtime and background behavior |
| Messaging relay | Native HTTPS/WebSocket clients, FastAPI and PostgreSQL ciphertext inbox | Background wakeups and public workload capacity; live foreground exchange passed |
| E2EE | Official libsignal Swift/Java bindings, pinned 0.105.0 | Physical lifecycle, corresponding-source release and distribution review; native interoperability passed |
| Identity | Shared Fallsoft WorkOS AuthKit, native PKCE | Current signed-client callback, session and deletion lifecycle |
| Account/control API | Stateless API backed by PostgreSQL | Current client integration with verified billing, push and bot provider behavior |
| Local translation | Apple Translation / Google ML Kit | Automatic full-message requests; actual model/direction, semantic and lifecycle qualification |
| Transliteration | Live native/library reading adapters and licensed Pinyin data | Complete readings, Chinese tones and ambiguous readings across the supported scripts |
| Speech | Native device voices with bundled eSpeak fallback and joined audio | [Local language support](LOCAL_LANGUAGE_SUPPORT.md) records device eligibility, expanded synthesis coverage and pending listening checks |
| Push | APNs and FCM, wake hints without message body | Delivery and force-quit limitations tested/disclosed |
| Purchases | StoreKit 2 / Google Play Billing; Apple official server SDK and Google subscriptions v2 | Store products and actual sandbox lifecycle receipts |
| vBot | Separate response-only DeepSeek gateway with atomic personal/global budgets | Real provider quality, latency and spend qualification |
| Domains | mambovipi.app registered through AWS Route 53 Domains; api.mambovipi.app live | Apex DNS and final store association files; AWS session renewal pending |
| Local models | Platform-managed translation and voice downloads | Actual preparation, offline use, recovery and storage controls |
| Initial hosting | Consolidated `fallsoft-production-20261106`; existing Storage Box for retained source/data | Full disaster recovery and public capacity; migration and scoped rollback receipts retained |

## Native boundaries

Each app implements its own UI, orchestration, immersion renderer, translation adapter, downloader, speech adapter, local database and lifecycle behavior. Share JSON schemas, protocol fixtures, design tokens, licensed transliteration data and test vectors. Reusing a maintained cryptographic library's native bindings is allowed; do not build a new shared application engine or invent cryptography.

The user approved open-source clients. The encryption spike now uses official libsignal Swift and Java bindings at the same pinned version, replacing the older Signal-C adapter candidate. The transport can carry opaque Signal envelopes without implementing cryptography. This is not Signal network interoperability. Native durable stores and transport-independent message journals now have qualification tests. Real relay integration, identity-change UX, key rotation, source-release packaging and release licensing remain required before production. Upstream does not support third-party use; Vipi owns dependency qualification and upgrades. Do not deploy placeholder encryption while this is pending.

## Account and device

WorkOS authenticates a person; it does not hold their message-decryption identity. The API maps the verified subject to a stable opaque Vipi user ID. Public usernames are independently normalized, reserved, rate-limited and discoverable only through exact lookup or invitation, not bulk directory enumeration.

Native OAuth uses system authentication sessions, PKCE, state and exact redirect validation. Secrets remain on the backend. Short-lived service credentials bind user and active device. Device identity keys are generated and protected on the phone using Keychain/Keystore-backed storage. New phone registration explicitly revokes the previous device and changes the visible chat identity unless a validated transfer preserves it. Email recovery does not decrypt lost messages.

## Sending and receiving

1. Compose persists a plaintext local record in protected local storage, with a random stable message ID and original timestamp, before a network send.
2. The sender encrypts for the trusted recipient identity. No plaintext fallback. Identity changes require explicit resolution.
3. The relay validates authentication, recipient policy, sizes and the immutable delivery deadline. It durably accepts a ciphertext envelope, then acknowledges acceptance. Client time cannot extend the allowed TTL; server-enforced bounds and retry identity must be tested.
4. Receiver verifies/decrypts and commits the message and deduplication marker durably before acknowledgement.
5. The relay deletes pending ciphertext after application-level durable receipt or absolute expiry. Transport acknowledgement alone is insufficient proof of application persistence.
6. Sender's durable outbox retries with backoff and jitter using the same ID and original deadline. Retries stop on acceptance plus final delivery, permanent rejection or expiry as appropriate. Receiver deduplicates across reconnect/crash.

State vocabulary: queued locally, accepted for delivery, delivered, failed, expired. Read receipts are separate, optional metadata. A manual resend after expiry creates a new message with a new deadline. Automatic retry never resurrects expired messages.

The implemented relay uses PostgreSQL transactions and ordered account locks. It does not run ejabberd or XMPP. Ciphertext expires 72 hours after the original send time, bounded by the server clock, and is cleared after durable recipient receipt. Audit database backups, WAL and operational retention so the public deletion description matches retained data. Logical expiry is distinct from physical erasure of backup media.

Push payload contains an opaque wake/event identifier only. The app reconnects and retrieves encrypted envelopes. OS background limits mean silent push is not a guaranteed live connection; design visible notification behavior and retries from measured platform behavior. Never keep a permanent Android foreground service solely to fake reliable delivery.

## Native durable messaging implementation

`MessageVault` uses native SQLite transactions with WAL and FULL synchronization. Record values are authenticated/encrypted with AES-256-GCM, using a per-account Android Keystore key or an iOS Keychain key marked AfterFirstUnlockThisDeviceOnly. Associated data binds the version, account, record kind and opaque record ID. No homemade cipher or ratchet is introduced. Record kinds and opaque IDs remain SQLite metadata; this is not a claim of whole-file encryption or protection against rollback of a complete compromised-device snapshot.

Android stores files under noBackupFilesDir with app backups disabled. iOS excludes the containing directory from backups and requests complete-until-first-authentication file protection. The device-enforced protection still needs physical validation. Missing storage keys do not trigger silent replacement while a database exists. All record access requires a synchronous transaction; network awaits must occur outside it. SQLite serializes writers across connections. No mutable session cache survives rollback.

`DurableSignalStore` implements the pinned native libsignal callbacks, including identities, sessions, classical/signed/post-quantum prekeys and the sender-key interface. Changed identities are rejected for sending and receiving. An explicit verified replacement flow, prekey allocation/rotation and group qualification remain open. Key types are not represented by application-defined cryptography.

`MessageJournal` saves the outgoing text to an encrypted draft before encryption/session work, retaining it across failures and restarts. Drafts have the same immutable deadline. It atomically commits ratchet mutations with the outgoing ciphertext or received plaintext/deduplication record. A retry reads identical saved ciphertext without advancing the ratchet again. The encrypted payload binds message ID, sender, recipient and creation time, which are checked against relay metadata after decryption. Receiver acknowledgement belongs after the commit returns. Incoming duplicate IDs with changed content are rejected. Original creation time fixes the 72-hour delivery deadline. A late authenticated delivered status may resolve a local expiry, but stale statuses cannot regress delivered history. Public transport still must authenticate status responses and enforce its own deadline.

These components are connected to native conversation and delivery workers. Actual authenticated native exchange, foreground arrival/reconnect, persisted delivery receipts and cross-platform encrypted history export/import have passed against the public restricted relay. Physical background recovery, final release storage migration and complete disaster recovery remain open; authored fixtures alone do not establish those outcomes.

## Public key directory and native HTTP integration

The control API now stores only public Signal identity/signed/prekeys. A publication contains at most 20 paired classical/Kyber1024 one-time keys, with a pool cap of 200. Revision and increasing key-ID checks prevent a retried upload from restoring consumed keys. Claim allocation and deletion share a PostgreSQL transaction; request-ID retries return the same bundle for ten minutes. Claim metadata expires after 72 hours when the cleanup function is scheduled. Blocking and device replacement use the same ordered user locks. Device replacement clears the old public pool; an ORM identity-map revocation race was explicitly reproduced and fixed.

Both native clients commit private prekeys and the pending upload before network work, rotate the signed key on a new publication after seven days, and verify incoming signatures with official libsignal. Private unused/retired-key cleanup is not yet implemented; do not claim a complete key lifecycle. Exhausted pools refuse new session establishment instead of falling back to reused or classical-only keys. Existing sessions can continue. Session establishment records the claimed device and a semantic bundle digest atomically, so a retried claim cannot reset an existing ratchet.

`MessagingCore` binds the persisted message to its original recipient device, validates incoming device routing inside the receive transaction, and uses the native journal for cryptographic operations. `ServiceClient` has no redirect following or response cache; its production path requires HTTPS. A debug-only loopback HTTP exception supports isolated QA. No credentials or plaintext message logs are added. WorkOS refresh is serialized and bound to the original account/session generation; stale responses after sign-out/account changes cannot restore the prior account. Actual refresh and API authentication passed on both platforms. Provider session revocation, logout and browser callback completion still need end-to-end release tests.

The first native qualification used private SSH/ADB forwards and was followed by real conversation UI exchange through public TLS on the consolidated host. The current foreground event path uses authenticated WebSocket headers and a content-free coalesced inbox hint after the database transaction commits. Bounded per-device/per-worker connections and reconnect backoff prevent an unbounded event queue. Both native clients received messages hands-off with notification permission denied; actual APNs/FCM background delivery remains open. No ejabberd/XMPP service is part of this implementation.

## Local immersion pipeline

The current contract is [Full-message immersion](FULL_MESSAGE_IMMERSION.md), replacing all earlier dictionary and fractional-word selection designs. Every new sent or received message reaches a native, account-owned full-message translation service. Complete results and live transliteration are cached in the account's encrypted vault; the authenticated authored original stays unchanged. Source detection is advisory and bounded, with the user's native language as fallback.

The chat shows one complete practice-language message, using live transliteration by default where needed. Tap plays practice-language audio; hold reveals meanings across the visible chat; double-tap switches script. A header toggle enables ordered automatic playback of new messages, with explicit stop and lifecycle cancellation. No timed word cycling, authored sentence lookup or translation dictionary remains in the shipping route.

Native model availability, actual provider output, phonetic reading, acoustic quality and UI behavior require separate evidence. The current local adapters do not send chat text to a translation server. Native macOS testing does not stand in for iOS app execution; compatible device testing remains necessary for the iOS ML Kit path.

## vBot and billing

vBot is a separate conversation type. Explicit consent explains that its messages and selected context go to the Vipi gateway and DeepSeek. Human chats are never automatically added as bot context. The gateway verifies identity, base entitlement and Bot mini entitlement before each request. Client-supplied conversation history remains untrusted and is bounded by token and size limits.

The gateway reserves the worst-case input/output cost atomically in PostgreSQL before contacting the provider. A unique request ID prevents retry duplication. Settle recorded usage, release unused reservation after verified terminal outcomes, and retain uncertain reservation rather than permitting overspend after a timeout. Enforce per-account/provider concurrency and global budget limits. Disable provider reasoning mode for response-only operation, pin the model, cap input/output, stream safely, and account for context as well as output. Usage events contain tokens and billing metadata, not message text. No prompt or response logging by default.

Store transactions are verified server-side. Apple historical signed transactions are checked against current subscription status. Google purchases are fetched from subscriptions v2, account/product/annual-plan checked, then acknowledged after persistence. Store references are encrypted with a purpose-separated key. Bind Apple appAccountToken to the internal Vipi account UUID; Google obfuscatedExternalAccountId is SHA-256 of `co.fallsoft.vipi:` plus that UUID. Authenticated Apple V2 and Google RTDN events enqueue current-status reconciliation; they never grant access directly. A bounded worker also reconciles daily. Ordinary chat reads the verified grant without a store request. During a store outage, previously verified access continues only until the earlier of its actual expiry and 72 hours since verification; beyond that the service returns unavailable rather than inviting another purchase. Superseded Google tokens cannot become active again. Base and Bot mini have separate store products and independent trial eligibility; Apple requires separate subscription groups. Dates and prices come from verified store data. Historical local data remains accessible after lapse. See [store reconciliation](STORE_RECONCILIATION.md) for configuration and qualification gates.

The implemented gateway initially returns one bounded reply, with no provider tools or reasoning mode. Client history contains only the chosen vBot conversation, at most 12 messages and 8,192 UTF-8 bytes. Candidate defaults are 150 replies per UTC calendar month and 384 output tokens per response. A $0.50 personal monthly cost ceiling and separate deployment-wide ceiling are enforced before dispatch. These configuration values await real provider measurements and store activation. Unknown provider outcomes retain their reservation and never automatically repeat the request. Ordinary generation stores no prompt/response content. User-confirmed reports retain only selected vBot text, encrypted, for 30 days or until account deletion; reports do not promise a support reply.

`GET /v1/entitlements` exposes `purchases_ready.apple/google`; checkout stays disabled until its verifier is configured. `GET /v1/bot/allowance` separately exposes `service_ready`, remaining reply count and reset date. Configured credentials do not establish successful store sandbox transactions or real inference qualification.

APNs and FCM registrations bind to the current active device. The push outbox coalesces inbox changes, uses bounded leases/retries and suppresses drained, expired or replaced-device inboxes. Payloads contain no human message text, sender identity or ciphertext. APNs uses a generic visible alert and inbox-change hint; Android receives a high-priority data hint and posts a local generic notification after bounded inbox work. Actual OS delivery and permission behavior still require live validation.

## Backups and recovery

User-initiated encrypted archive export to their chosen storage. No unbounded server history or backup bucket is implied by the subscription. The archive uses a maintained cryptographic primitive/library, authenticated versioned metadata, and a recovery secret unavailable to the relay. Restore validates integrity, limits resources, and commits atomically. Document lost recovery-key behavior. Keys and plaintext must not leak into generic OS automatic backups, analytics, logs, push payloads or previews.

Operational metadata backups use the existing consolidated daily controller and retain up to three verified encrypted generations. They exclude relay rows, public bundles/prekeys/claims, push data and report bodies. The current database's authenticated decryption, tamper rejection and twenty-table isolated restore have passed; this is separate from customer history export. A restored candidate stays disconnected from API and workers until fresh deletion/restriction state is reconciled, restored device credentials are invalidated, subscriptions and uncertain bot spend are reverified, and native re-enrollment is qualified. Missing post-snapshot evidence blocks reopening. Three generations do not imply a fixed retention duration or a qualified recovery-time objective. The opt-in `VIPI_RECOVERY_HOLD=true` startup configuration prevents API/WebSocket state paths and deployed workers from initializing database/provider clients; readiness fails while static guidance remains available. It must be set consistently before restored processes start. It neither detects restores automatically nor verifies reconciliation authority, and offline reports cannot release it.

## Deployment and growth

The former OZZZ CPU/GPU hosts are retired. Vipi's API and dedicated database run on the consolidated production host, with a separate runtime user, database privileges and private API listener behind HTTPS ingress. New Apple builds and QA use native `apple@macbook-pro`; the former development VM was preserved and retired on November 9. Preserve other workloads and existing QA environments. Deploy Vipi changes with explicit source/dependency manifests, database migration/backup receipts and scoped service restart.

Measure message throughput, p50/p95/p99 latency, CPU/RAM, reconnect storms, foreground polling, backlog and queue-age bounds. Scale stateless API and push workers from those measurements, then database capacity and transport changes when justified. Translation models are managed by platform provider APIs. A million registered or paying accounts is not a concurrent connection count or demonstrated capacity.

Observability is content-free: request/error counters, delivery latency, active connections, queue expiry, database health and spend. Redact credentials and contact text. Alert on budget/retention failures, create restorable operational backups and exercise rollback before public release.

The former staging host and OZZZ development hosts are retired and must not be reconnected or recreated. The consolidated service has its own runtime user, database/roles, immutable release directories and expiry/billing timers. New changes preserve shared PostgreSQL/nginx processes and other applications. Source authority is the reconciled delivery checkout; native Apple work uses the verified committed-source mirror described in `BUILD_ENVIRONMENTS.md`. Copied historical directories are not independently authoritative.

`ops/` contains scoped service and nginx configurations; `scripts/package-service.py` builds an immutable dependency/source manifest and archive. Alembic 1.20.1 owns schema migrations; initial revision `20261025_01` was checked against the ORM and repeated without losing data. Readiness checks the migration head. Staging requires an explicit allowlist of already verified WorkOS subjects, so deploying a QA endpoint does not open public registration. The minute expiry task clears expired ciphertext and aged delivery/key-claim/rate metadata. An nginx reload for a new vhost must be syntax-checked and followed by existing-site checks; no shared service restart, firewall change or database restart is planned.

The service at `https://api.mambovipi.app` runs on consolidated `fallsoft-production-20261106`. The completed November 17 configuration-only activation enabled production mode, subscription enforcement and Apple Production, and removed the restricted-subject allowlist. Its independent postflight confirmed readiness, unauthenticated-request rejection, migration `20261117_01`, and preservation of unrelated services; no schema or database restoration occurred. This is a reconciliation of the retained activation receipt, not a new deployment or a fresh live-status assertion. Current rollout and release evidence is in [DELIVERY_STATUS.md](DELIVERY_STATUS.md). Earlier foreground delivery and 72-hour expiry evidence is retained. The separate two-worker loopback experiment with 192 sockets and 480 exchanges is a bounded experiment, not public or million-user capacity proof. Production backend configuration does not establish app-store availability.
