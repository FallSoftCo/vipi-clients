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

Stock ejabberd offline queues/MAM are not assumed to implement these semantics. Verify the exact hooks/modules needed; disable persistent MAM for launch unless a bounded ciphertext-only implementation is proven. Audit offline storage, stream-management queues, logs, database backups, WAL and operational retention so the public deletion description matches what is actually retained. Don't claim physical erasure at a precise second if the system only offers logical expiry plus later cleanup.

Push payload contains an opaque wake/event identifier only. The app reconnects and retrieves encrypted envelopes. OS background limits mean silent push is not a guaranteed live connection; design visible notification behavior and retries from measured platform behavior. Never keep a permanent Android foreground service solely to fake reliable delivery.

## Native durable messaging implementation

`MessageVault` uses native SQLite transactions with WAL and FULL synchronization. Record values are authenticated/encrypted with AES-256-GCM, using a per-account Android Keystore key or an iOS Keychain key marked AfterFirstUnlockThisDeviceOnly. Associated data binds the version, account, record kind and opaque record ID. No homemade cipher or ratchet is introduced. Record kinds and opaque IDs remain SQLite metadata; this is not a claim of whole-file encryption or protection against rollback of a complete compromised-device snapshot.

Android stores files under noBackupFilesDir with app backups disabled. iOS excludes the containing directory from backups and requests complete-until-first-authentication file protection. The device-enforced protection still needs physical validation. Missing storage keys do not trigger silent replacement while a database exists. All record access requires a synchronous transaction; network awaits must occur outside it. SQLite serializes writers across connections. No mutable session cache survives rollback.

`DurableSignalStore` implements the pinned native libsignal callbacks, including identities, sessions, classical/signed/post-quantum prekeys and the sender-key interface. Changed identities are rejected for sending and receiving. An explicit verified replacement flow, prekey allocation/rotation and group qualification remain open. Key types are not represented by application-defined cryptography.

`MessageJournal` saves the outgoing text to an encrypted draft before encryption/session work, retaining it across failures and restarts. Drafts have the same immutable deadline. It atomically commits ratchet mutations with the outgoing ciphertext or received plaintext/deduplication record. A retry reads identical saved ciphertext without advancing the ratchet again. The encrypted payload binds message ID, sender, recipient and creation time, which are checked against relay metadata after decryption. Receiver acknowledgement belongs after the commit returns. Incoming duplicate IDs with changed content are rejected. Original creation time fixes the 72-hour delivery deadline. A late authenticated delivered status may resolve a local expiry, but stale statuses cannot regress delivered history. Public transport still must authenticate status responses and enforce its own deadline.

This implementation is not yet connected to the real conversation UI or a production transport. Delivery workers, scheduling/backoff, unread/paging, receipt retry behavior, transactional identity replacement, storage migration and full encrypted backup/restore remain release gates.

## Public key directory and native HTTP integration

The control API now stores only public Signal identity/signed/prekeys. A publication contains at most 20 paired classical/Kyber1024 one-time keys, with a pool cap of 200. Revision and increasing key-ID checks prevent a retried upload from restoring consumed keys. Claim allocation and deletion share a PostgreSQL transaction; request-ID retries return the same bundle for ten minutes. Claim metadata expires after 72 hours when the cleanup function is scheduled. Blocking and device replacement use the same ordered user locks. Device replacement clears the old public pool; an ORM identity-map revocation race was explicitly reproduced and fixed.

Both native clients commit private prekeys and the pending upload before network work, rotate the signed key on a new publication after seven days, and verify incoming signatures with official libsignal. Private unused/retired-key cleanup is not yet implemented; do not claim a complete key lifecycle. Exhausted pools refuse new session establishment instead of falling back to reused or classical-only keys. Existing sessions can continue. Session establishment records the claimed device and a semantic bundle digest atomically, so a retried claim cannot reset an existing ratchet.

`MessagingCore` binds the persisted message to its original recipient device, validates incoming device routing inside the receive transaction, and uses the native journal for cryptographic operations. `ServiceClient` has no redirect following or response cache; its production path requires HTTPS. A debug-only loopback HTTP exception supports isolated QA. No credentials or plaintext message logs are added. WorkOS refresh is serialized and bound to the original account/session generation; stale responses after sign-out/account changes cannot restore the prior account. Actual refresh and API authentication passed on both platforms. Provider session revocation, logout and browser callback completion still need end-to-end release tests.

The first real native network qualification used this HTTP data path with a real WorkOS verifier and isolated PostgreSQL, reached through private SSH/ADB forwards. It proves neither production TLS nor ejabberd/push/background behavior. The temporary service, forwards and database were removed after all four messages were delivered and their server ciphertexts cleared. Real conversation UI and production relay/event integration remain required.

## Local immersion pipeline

Original message -> language detection -> whole-sentence/paragraph local translation -> local word/phrase alignment against a licensed bilingual pack -> conservative candidate filtering -> density/familiarity selection -> attributed visible spans.

Keep original text immutable. Cache derived translations locally by source text hash, direction, provider/model version and pack version. Expire affected caches when these change. Shared fixtures specify UTF-8 text plus Unicode-aware ranges; platform adapters explicitly convert indexing rather than assuming Swift and Kotlin offsets are identical.

Translation APIs provide full text, not reliable token alignment. Dictionary candidates must be corroborated in the actual full translation and constrained by context, morphology and phrase boundaries. Multiple possible senses, repeated words or uncertain alignment reduce confidence; abstain rather than display a confident wrong replacement. This approach needs measured precision and coverage. If it cannot meet quality targets, improve the local alignment technique before expanding language claims.

The next data path expands the catalog into contextual word/phrase records, inflected forms, sense-specific mappings and native-script readings. Precompute this work before distribution, using licensed dictionaries and attested aligned examples first, then evaluated generation where coverage is missing. Ship searchable data; retain separate Swift and Kotlin runtime implementations. Local full-text retrieval finds candidates from the message's actual sentence/paragraph. Selection must consider the meaning, competing senses, phrase boundaries and reading evidence; search relevance alone never authorizes a replacement. Measure incorrect substitutions as well as useful coverage on untouched acceptance data. The research builder retains explicit aligned usage-example spans and provenance. Separately assessed frame/context exports cover 110 directed pairs in the native chat path. Research candidates still require review before promotion; broad coverage, arbitrary readings and production distribution remain open.

The mapping unit is a word or phrase **in a particular meaning**, not an arbitrary source spelling. Keep its attested written/inflected forms, grammatical and register evidence, source-language contexts, target forms and readable transliteration together with provenance. Retain exact focus spans in both example sentences: copying an example's target phrase can otherwise import a person or possession absent from the new message (for example, `de camino` → `on my way` in a request addressed to someone else). Phrase constraints remain unresolved unless established by data or evaluated generation. FTS results are candidates for the native selector; incidental shared context words must not make them display-ready.

Build the catalog incrementally with SQLite: immutable record revisions, exact provenance, transactionally committed input checkpoints, per-revision assessments and correction/quarantine history. Export compact per-pair client data separately. PostgreSQL/pgvector is not needed on the phone or in the catalog build path. A future local embedding index must earn its place through better measured meaning selection; the existing vector experiments have not done so.

Supplement whole-message local translation with bounded word/phrase observations where useful. Cache by exact text, direction and data/provider version; changing `my` to `your` must not reuse a sentence translation. Phrase agreement supplies alignment evidence, not an independent meaning verdict. Keep authored context patterns finite: literals, enumerated variations outside one lexical focus, and target forms/readings attached to that meaning. Preserve original characters outside the focus. Native Kotlin/Swift matchers implement this constraint separately; the approved bundled context/frame catalogs now run in the actual native conversation components, with a bounded per-conversation cache and immutable sender originals. Broad conversational coverage remains unproven.

Use existing concept-linked dictionaries to broaden coverage before generating missing records. The pinned [Cygnet release](https://github.com/omwn/cygnet/releases/tag/2026.05.12) supplies a second research source with explicit multilingual concepts and source-sense examples. Preserve its per-row provenance and resource licenses; the repository's MIT code license does not license all the underlying data. Never merge a Wiktionary sense with a WordNet concept merely because their headwords match. Generation may fill missing meanings, contexts, forms and readings at build time, with its model/version, inputs, outputs and evaluation retained. No network model is added to runtime immersion. Native full-thought translation and local TTS remain independent features.

Native pack schema 4 preserves every catalog sense associated with a source spelling that has at least one eligible mapping, including senses with no target mapping. These empty-target entries supply ambiguity and contrary-context evidence. Count sense identities, not identical gloss strings. This prevents target-language coverage from erasing source ambiguity; it does not claim the underlying source catalog is complete.

Keep grammatical source phrases native when every whitespace-delimited component is an attested function word. This closes multiword `do not` escaping the original single-spelling filter. It does not remove lexical phrases just because they contain a function word, and it does not infer segmentation for unspaced scripts.

Pack manifest: schema version, pack ID, language tags, license/provenance, build ID, compressed/uncompressed size, content SHA-256, signing key ID and signature. Download to a bounded temporary file, verify signature/hash/schema, atomically install, preserve the previous valid pack on failure, and expose cancellation/removal/storage usage. Prevent path traversal, decompression bombs, stale manifest rollback and silent incompatible schema installation. Provider translation models are downloaded through native provider APIs, not redistributed as our files.

Desired eventual coverage is 80 languages. Launch picker reflects the intersection of provider direction support, installed model capability, tested vocabulary packs and available speech; display capability differences honestly. No 80-language launch claim until verified. Start the engineering spike with English/Spanish and add representative morphology, non-Latin and RTL fixtures before broad rollout.

The native presentation layer owns continuous immersion clocks, separate from translation and pack processing. Only visible, active, unpaused messages alternate; scrolling/selection/audio and screen readers suspend the clock. Defaults are 4.5 seconds target vocabulary and 3 seconds familiar meanings, with persistent pace choices. The renderer uses native paragraphs with fixed vocabulary blocks. Android ReplacementSpan retains source ranges for stable bidi layout and draws the active face; iOS text attachments reserve all faces’ maximum dimensions. Both use a faint background with 2.5-point rounding, and preserve readable selection/copy output. The local presentation wrappers own this behavior; no shared cross-platform UI engine is introduced. Swift and Kotlin own their implementation; only authored examples and fixture contracts are shared. Native token boundaries constrain candidate matching, and protected spans in both original and translation cannot corroborate vocabulary replacements.

The bundled eleven-language conversation previews, including Swahili, are expressly authored demonstrations. They do not represent a production multilingual pack, arbitrary-message transliteration or platform translation output. The Apple physical-device QA route prepares native models and records actual direction-by-direction output and network state; simulator availability cannot replace that receipt.

Speech is owned by the active conversation's language pair. Both installed native voices are selected and silently warmed before Listen becomes ready, then retained for that conversation. This does not guarantee OS-level model residency. Visible transliteration maps back to the original target script for synthesis. Word reveals, reading-mode changes, navigation and audio interruptions invalidate queued work and stop playback.

Short messages render to one PCM file; longer messages use bounded local rendering into one continuous native output: Android AudioTrack, iOS AVAudioEngine/AVAudioPlayerNode. No separate player is created for each word. Keep generated speech caches bounded to 64 MiB per app and rebuild derived audio when the reading state or voices change. Brief pauses can help comprehension and are preserved for listening evaluation; optimize predictable startup and prevent accidental stalls without assuming zero silence is desirable. See [speech qualification](SPEECH_QUALIFICATION.md) for measurements and limits.

The incremental context engine has native Kotlin and Swift implementations. A matched context can supply an ephemeral source scope bound to the exact original message and lexical offsets, plus attested target forms with explicit inner lexical offsets. These allow a noun inside an attached article/particle token without introducing generic stemming or replacing surrounding grammar. Generic dictionary JSON cannot persist those ephemeral capabilities. Unscoped entries retain ordinary native word-boundary checks; protected text, ambiguous meanings, required readings and contrary context still constrain selection. Straight and curly apostrophes compare equivalently without rewriting stored/displayed strings. These components now run in general friend chat using app-bundled, hash-checked exports from the authoring ledger. Downloadable production updates and broad meaning/coverage acceptance remain open; synthetic chat qualification is not live messaging proof.

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

Initial staging target selected after read-only checks: existing `ozzz-app` (`ssh ozzz-root`, hostname `ubuntu-16gb-ash-1`). At inspection it had about 12.7 GiB available memory, 51 GiB disk free and low CPU load. It already runs PostgreSQL 16 and nginx. Vipi gets its own Unix account, database/roles, immutable release directory, service and expiry timer. All dependency preparation occurs on OZZZ-OS; both hosts use Ubuntu 24.04, CPython 3.12.3 and x86_64. No existing app/database/service is replaced.

`ops/` contains scoped service and nginx configurations; `scripts/package-service.py` builds an immutable dependency/source manifest and archive. Alembic 1.20.1 owns schema migrations; initial revision `20261025_01` was checked against the ORM and repeated without losing data. Readiness checks the migration head. Staging requires an explicit allowlist of already verified WorkOS subjects, so deploying a QA endpoint does not open public registration. The minute expiry task clears expired ciphertext and aged delivery/key-claim/rate metadata. An nginx reload for a new vhost must be syntax-checked and followed by existing-site checks; no shared service restart, firewall change or database restart is planned.

The restricted staging service is deployed at `https://api.mambovipi.app`, with real native public-HTTPS delivery, TLS renewal rehearsal and 72-hour expiry cleanup qualified. It has not been load-qualified. Production registration, public policy pages, session revocation, ejabberd/push and backup/restore operations remain release gates.
