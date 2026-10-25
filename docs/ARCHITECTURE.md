# Architecture

## Components

| Concern | Choice | Qualification still required |
|---|---|---|
| iOS | Swift, SwiftUI, native concurrency and platform storage | Swift/Xcode build and simulator coverage |
| Android | Kotlin, Compose, coroutines, Room/SQLite, WorkManager | Build, emulator coverage, background behavior |
| Messaging relay | ejabberd/XMPP, private service with federation disabled | Enforced expiry, encrypted-only policy, retention and load tests |
| E2EE | Official libsignal Swift/Java bindings, 0.105.0 qualification candidate | Native interoperability, durable transactional key stores, identity verification and release license review |
| Identity | WorkOS AuthKit, native PKCE | Separate Vipi app, callback association and device binding |
| Account/control API | Small stateless API backed by PostgreSQL | Implementation and provider credentials |
| Local translation | Apple Translation / Google ML Kit | Actual device/model/direction availability; no alignment API assumed |
| Vocabulary | Versioned downloadable SQLite packs | Source licensing, provenance, contextual alignment quality |
| Speech | Native offline speech engines | Installed voice checks and mixed-language playback |
| Push | APNs and FCM, wake hints without message body | Delivery and force-quit limitations tested/disclosed |
| Purchases | StoreKit / Google Play Billing, server validation | Products, notifications, renewals, refunds, trial eligibility |
| vBot | Authenticated gateway to DeepSeek | Price/model pin, spend reservation, stream cancellation and limits |
| Domains | mambovipi.app registered through AWS Route 53 Domains | DNS, TLS and association files |
| Pack files | Static HTTPS object storage, cacheable and content-addressed | R2 candidate; confirm actual provider account and costs |
| Initial hosting | One existing small Hetzner app host | Capacity, owner, isolated deployment and rollback receipt |

## Native boundaries

Each app implements its own UI, orchestration, immersion renderer, translation adapter, downloader, speech adapter, local database and lifecycle behavior. Share JSON schemas, SQLite pack structure, protocol fixtures, design tokens and test vectors. Reusing a maintained cryptographic library's native bindings is allowed; do not build a new shared application engine or invent cryptography.

The user approved open-source clients. The encryption spike now uses official libsignal Swift and Java bindings at the same pinned version, replacing the older Signal-C adapter candidate. The transport can carry opaque Signal envelopes without implementing cryptography. This is not Signal network interoperability. Exact envelopes, transactional identity/session storage, native exchange and release licensing remain required before production. Upstream does not support third-party use; Vipi owns dependency qualification and upgrades. Do not deploy placeholder encryption while this is pending.

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

Stock ejabberd offline queues/MAM are not assumed to implement these semantics. Verify the exact hooks/modules needed; disable persistent MAM for launch unless a bounded ciphertext-only implementation is proven. Audit offline storage, stream-management queues, logs, database backups, WAL and operational retention so the public deletion description matches what is actually retained. Don't claim physical erasure at a precise second if the system only offers logical expiry plus later cleanup.

Push payload contains an opaque wake/event identifier only. The app reconnects and retrieves encrypted envelopes. OS background limits mean silent push is not a guaranteed live connection; design visible notification behavior and retries from measured platform behavior. Never keep a permanent Android foreground service solely to fake reliable delivery.

## Local immersion pipeline

Original message -> language detection -> whole-sentence/paragraph local translation -> local word/phrase alignment against a licensed bilingual pack -> conservative candidate filtering -> density/familiarity selection -> attributed visible spans.

Keep original text immutable. Cache derived translations locally by source text hash, direction, provider/model version and pack version. Expire affected caches when these change. Shared fixtures specify UTF-8 text plus Unicode-aware ranges; platform adapters explicitly convert indexing rather than assuming Swift and Kotlin offsets are identical.

Translation APIs provide full text, not reliable token alignment. Dictionary candidates must be corroborated in the actual full translation and constrained by context, morphology and phrase boundaries. Multiple possible senses, repeated words or uncertain alignment reduce confidence; abstain rather than display a confident wrong replacement. This approach needs measured precision and coverage. If it cannot meet quality targets, improve the local alignment technique before expanding language claims.

Pack manifest: schema version, pack ID, language tags, license/provenance, build ID, compressed/uncompressed size, content SHA-256, signing key ID and signature. Download to a bounded temporary file, verify signature/hash/schema, atomically install, preserve the previous valid pack on failure, and expose cancellation/removal/storage usage. Prevent path traversal, decompression bombs, stale manifest rollback and silent incompatible schema installation. Provider translation models are downloaded through native provider APIs, not redistributed as our files.

Desired eventual coverage is 80 languages. Launch picker reflects the intersection of provider direction support, installed model capability, tested vocabulary packs and available speech; display capability differences honestly. No 80-language launch claim until verified. Start the engineering spike with English/Spanish and add representative morphology, non-Latin and RTL fixtures before broad rollout.

The native presentation layer owns continuous immersion clocks, separate from translation and pack processing. Only visible, active, unpaused messages alternate; scrolling/selection/audio and screen readers suspend the clock. Defaults are 4.5 seconds target vocabulary and 3 seconds familiar meanings, with persistent pace choices. The renderer uses native paragraphs with fixed vocabulary blocks. Android ReplacementSpan retains source ranges for stable bidi layout and draws the active face; iOS text attachments reserve all faces’ maximum dimensions. Both use a faint background with 2.5-point rounding, and preserve readable selection/copy output. The local presentation wrappers own this behavior; no shared cross-platform UI engine is introduced. Swift and Kotlin own their implementation; only authored examples and fixture contracts are shared. Native token boundaries constrain candidate matching, and protected spans in both original and translation cannot corroborate vocabulary replacements.

The bundled ten-language conversation previews are expressly authored demonstrations. They do not represent a production multilingual pack, arbitrary-message transliteration or platform translation output. The Apple physical-device QA route prepares native models and records actual direction-by-direction output and network state; simulator availability cannot replace that receipt.

Speech is owned by the active conversation's language pair. Both installed native voices are selected and silently warmed before Listen becomes ready, then retained for that conversation. This does not guarantee OS-level model residency. Visible transliteration maps back to the original target script for synthesis. Word reveals, reading-mode changes, navigation and audio interruptions invalidate queued work and stop playback.

Short messages render to one PCM file; longer messages use bounded local rendering into one continuous native output: Android AudioTrack, iOS AVAudioEngine/AVAudioPlayerNode. No separate player is created for each word. Keep generated speech caches bounded to 64 MiB per app and rebuild derived audio when the reading state or voices change. Brief pauses can help comprehension and are preserved for listening evaluation; optimize predictable startup and prevent accidental stalls without assuming zero silence is desirable. See [speech qualification](SPEECH_QUALIFICATION.md) for measurements and limits.

## vBot and billing

vBot is a separate conversation type. Explicit consent explains that its messages and selected context go to the Vipi gateway and DeepSeek. Human chats are never automatically added as bot context. The gateway verifies identity, base entitlement and Bot mini entitlement before each request. Client-supplied conversation history remains untrusted and is bounded by token and size limits.

The gateway reserves the worst-case input/output cost atomically in PostgreSQL before contacting the provider. A unique request ID prevents retry duplication. Settle recorded usage, release unused reservation after verified terminal outcomes, and retain uncertain reservation rather than permitting overspend after a timeout. Enforce per-account/provider concurrency and global budget limits. Disable provider reasoning mode for response-only operation, pin the model, cap input/output, stream safely, and account for context as well as output. Usage events contain tokens and billing metadata, not message text. No prompt or response logging by default.

Store transactions are verified server-side. Persist original transaction/purchase-token binding, product, expiry, revocation and environment; authenticate and deduplicate webhooks. Never trust a client Boolean entitlement. Handle refunds, grace, billing retry, account switching and simultaneous store purchase attempts. Product and trial duration come from stores. Historical local data remains accessible after lapse.

## Backups and recovery

User-initiated encrypted archive export to their chosen storage. No unbounded server history or backup bucket is implied by the subscription. The archive uses a maintained cryptographic primitive/library, authenticated versioned metadata, and a recovery secret unavailable to the relay. Restore validates integrity, limits resources, and commits atomically. Document lost recovery-key behavior. Keys and plaintext must not leak into generic OS automatic backups, analytics, logs, push payloads or previews.

## Deployment and growth

Begin with isolated service units/containers, PostgreSQL, ejabberd and the control API on a suitable existing host. Separate secrets, database role and filesystem ownership from current workloads. Bind internal ports privately; use TLS and the existing ingress only after confirming owner and impact. Record host security ownership and provisioning receipts. No unrelated restart or firewall change.

Measure initial connection count, message throughput, p50/p95/p99 latency, CPU/RAM, reconnect storms, backlog and queue-age bounds. Horizontal growth adds ejabberd nodes in a low-latency region, connection-aware load balancing, independently scalable API/push workers and database capacity. Shard only after evidence. Object storage/CDN serves immutable packs. Model a million paying accounts with daily active and simultaneous-online assumptions; account count is not concurrency.

Observability is content-free: request/error counters, delivery latency, active connections, queue expiry, database health, pack downloads and spend. Redact credentials and contact text. Alert on budget/retention failures, create restorable operational backups and exercise rollback before public release.
