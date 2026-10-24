# Verification ledger

Updated 2026-10-24. Vipi is in implementation; it is not deployable or submitted to either store.

| Check | Result | Evidence / limits |
|---|---|---|
| AWS CLI | Passed after user login | CLI 2.34.11; STS and Route 53 Domains/DNS verified. Credentials remain outside source. |
| Domain | Registered successfully | mambovipi.app, operation 2b6b7fd9-ca43-4381-a661-b0be34b4ce26, terminal SUCCESSFUL at 2026-10-24 20:07:05 UTC. Expires 2027-10-24; auto-renew and contact privacy enabled. DNS/TLS deployment pending. |
| Linux workspace | In use | /aosp/development/vipi on OZZZ-OS; storage-guarded builds with the current 8 GiB floor. |
| Android build | Passed | artifacts/android-build-015.log on OZZZ; WorkOS 0.4.0, Kotlin 2.4.0. R8 9.5.28 override resolves bundled R8 incompatibility. Dedicated x86_64 QA APK excludes upstream JNI test/desktop binaries, reducing instrumentation APK from ~1.1GB to 119MB. Release packaging and repeat crypto test after packaging changes remain pending. |
| Android core | 7 tests passed | Includes duplicate-entry ambiguity regression. Native alignment and delivery-window fixtures, not a broad quality benchmark. |
| iOS build | Passed | Mac build-ios-003.log; native-packs-002.log tests use CODE_SIGNING_ALLOWED=YES and ad-hoc simulator signing. Unsigned simulator builds failed Keychain access (-34018). No signed release archive. |
| Swift core | 9 tests passed | Unicode ranges, protected spans, duplicate-entry ambiguity, speech spans and delivery deadlines. |
| Backend logic | 26 PostgreSQL tests passed | artifacts/backend-postgres-002.log; isolated PostgreSQL 16 container with no network, removed after test. Includes concurrent queue cap, retry deduplication, spending reservations and replacement/delivery races. JWT tests cover signature, issuer, client_id, expiry and unknown-kid rate bounds; API tests use synthetic principals. Real WorkOS token verification against live JWKS remains pending. First PostgreSQL run found a test error reading nonexistent BudgetError.code; corrected to str(error). |
| Android device tests | 2 passed | artifacts/android-device-001.log: actual ML Kit Spanish translation with both emulator radios off and activeNetwork=null; Keystore records survive reopen and reject corruption/record substitution. |
| UX captures | Welcome reviewed | iOS light/dark and Android light. Early transition/splash captures replaced with settled-screen captures; complete navigation/accessibility tests pending. |
| WorkOS | Staging configured | Separate Vipi app and native callback. App-scoped staging API key has seven-day expiry and is stored privately outside source. Dedicated synthetic QA account created; password exchange returns a five-minute token with issuer https://api.workos.com and client_id, no aud. Native browser sign-in, refresh and revocation tests pending. |
| Encryption | Native interoperability passed | Official libsignal 0.105.0, Android export/Swift decrypt/three Swift replies/Android decrypt in order 2,0,1. Both reject replays; Android rejects altered ciphertext. OZZZ artifacts/signal-android-export-001.log and signal-android-import-001.log; Mac signal-interop-001.log. Synthetic in-memory stores only; durable production stores and distribution qualification remain pending. |
| Vocabulary pack | Native installation and lookup passed | eng-spa revision 2, CC-BY-SA 3.0, database 3,031,040 bytes, SHA-256 3d051ae8bd0d1536945b51dd414603218a9c7f28122f9276386f0cce93fb20bb. P256 signature/hash checks, native SQLite lookup, corruption rejection and removal passed on both platforms. OZZZ native-packs-android-003.log; Mac native-packs-002.log. No network downloader or broad linguistic evaluation yet. |
| Android translation matrix | Execution covered; linguistic gate fails | artifacts/immersion/android-language-matrix-001.json: all 90 directed pairs, 540 nonempty outputs, network unavailable, median 110.3ms and p95 373.4ms on this emulator. Reviewed examples include Chinese→Japanese retaining an English sentence and Korean→Portuguese changing the actor. These are not 90 immersion UX passes. |
| Apple translation | Availability only | artifacts/immersion/apple-language-matrix-001.json reports all 90 directions supported on macOS. Translation cannot execute in iOS simulator. Both paired physical devices unavailable; user asked to connect one. No successful Apple translation execution claimed. |
| Transliteration | Generic conversion rejected | artifacts/immersion/apple-transliteration-001.json: generic transform reads Japanese kanji as Chinese and mishandles Chinese polyphones; language-aware tokenizer improves tested Chinese/Japanese examples. Arabic output is consonantal/notation-heavy and not accepted as readable immersion. No full non-Roman transliteration implementation accepted yet. |
| Native speech | Rendering experiment only | iOS native-speech-002.log exports ten language samples. Prepared en/es produces one mixed PCM file in ~121.5ms, cached preparation ~0.19ms. First English selection picked legacy Fred; selection corrected but rerun pending. No listening or UI acceptance yet. Android first offline run found no ready voices; native voice-data installation in progress. |
| Company policies | Source and live pages inspected | FallSoft.Co policy dated July 23, 2026; product-specific disclosures pending. |
| Backend deployment | Not started | No chosen production host or public Vipi listener yet. |
| Stores | Not submitted | Company signing identity exists; app records, products, releases and review packages pending. |

## Evidence requirements

Retain source revision, dependencies, build/version, device/runtime, command, timestamp, outcome and artifact path. Keep contact details, signing keys, OAuth verifiers and real message/key material outside public receipts.

Encryption needs native exchange, replay/tamper/out-of-order rejection or handling, transactional persistence, identity replacement and server/network plaintext inspection. Local immersion needs actual translation with networking disabled. Billing needs verified sandbox transactions, refund/revocation/restore and forged-token rejection. UX needs interaction and accessibility checks. Load needs reproducible resource and latency measurements.
