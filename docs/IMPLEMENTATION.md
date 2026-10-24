# Implementation sequence and release gates

Every gate needs a retained command/build/device receipt. A screenshot proves appearance, not encryption, billing or delivery correctness. No store submission until the release-blocking gates pass.

## Current priority — user directive, 2026-10-24

Demonstrate the core immersion UX across at least ten major languages and every directed pair, including transliteration for non-Roman scripts. Initial qualification set: English, Spanish, French, German, Italian, Portuguese, Arabic, Mandarin Chinese, Japanese and Korean. This is 90 directions per platform, 180 platform/direction combinations. Do not substitute a download/availability check, English-only pivot example or isolated welcome screenshot for this proof. See IMMERSION_ACCEPTANCE.md. Infrastructure work already started is retained, but broader deployment and store work follow this gate.

## 1. Foundations and decisions

- [x] Record product, architecture, data boundaries and release sequence.
- [x] Verify OZZZ-OS Android tools, Mac Xcode/simulators and company signing identity exist.
- [x] Renew AWS CLI and verify Route 53 domains/DNS access.
- [x] Select inexpensive AWS domain with registration AND renewal cost: mambovipi.app, AWS registration successful.
- [ ] Choose host after capacity/workload inspection and ownership registration.
- [ ] Confirm crypto library licenses and interoperable protocol version.
- [ ] Record build mirrors, dependency pins, reproducible commands and credentials inventory (locations only).

## 2. Prove the hard paths

- [ ] Native iOS <-> Android E2EE through a private ejabberd test instance: initial keys, first message, ratchet, offline reply, replay, wrong key, tamper, device replacement.
- [ ] Durable delivery receipt, crash recovery, deduplication and immutable 72-hour deadline with controllable clock tests.
- [ ] Whole-message local translation on both platforms, network-disabled after download.
- [ ] Contextual alignment benchmark, with measured precision/coverage and explicit abstentions, not just a canned demo.
- [ ] Mixed-language and full-language speech using local voices on each platform.
- [ ] Store trial/purchase and WorkOS native redirect feasibility in the actual accounts/environments.

## 3. Native product

- [ ] Design tokens, native theme preference, accessibility foundation and routing.
- [ ] Welcome/interactive immersion preview, language selection, download state, authentication, username, trial, first-chat onboarding.
- [ ] Real chat list, compose/invite/exact lookup, friend conversation, vBot conversation.
- [ ] Local persistence/outbox, timestamps, delivery states, unread/navigation restoration, paging and keyboard behavior.
- [ ] Original/mixed/full translation in-place rendering, contextual reveal, copy, selection and speech.
- [ ] Settings: languages/storage, immersion density, appearance, account, subscriptions, backup, privacy, block/report/delete.
- [ ] Offline, empty, denied permission, missing voice/model, expired delivery, refund, revoked device and retry states.

## 4. Service and data

- [ ] Authenticated API, WorkOS validation, account mapping/device credentials and unique usernames/invitations.
- [ ] ejabberd encrypted-only policy, bounded pending delivery, public bundles, blocking, rates and abuse controls.
- [ ] Contentless APNs/FCM integration with proven platform behavior.
- [ ] Pack compiler, provenance/license manifest, signed distribution and atomic native installers.
- [ ] Verified subscription state, webhook idempotency, restore and deletion.
- [ ] vBot bounded streaming gateway, pricing configuration, cost ledger, monthly quota and failure recovery.
- [ ] User-controlled encrypted backups, authenticated restore and identity-transfer rules.

## 5. Experience and operations

- [ ] Mobbin review of onboarding, chat, settings and purchase flows; retain reference links and original design decisions.
- [ ] Built for Mars critique of actual implemented screens and failure flows; apply useful findings and document disagreement.
- [ ] iOS and Android screenshots in light/dark, smallest/large screen, large text and RTL. Inspect every critical screen.
- [ ] TalkBack/VoiceOver semantics, reduced motion, screen rotation, keyboard, background/relaunch and interrupted onboarding.
- [ ] Load/reconnect/backlog tests with measured resource costs and realistic media-free usage assumptions.
- [ ] Security review of authentication, key storage, encryption, metadata/logs, backup, deletion, dependency licenses and report consent.
- [ ] Isolated deployment, TLS, DNS, pack hosting, operational metrics, restore/rollback drill and security ownership receipt.

## 6. Store release

- [ ] Confirm current Apple/Google policy requirements, age rating, subscription disclosures, export compliance and privacy labels/data safety.
- [ ] Product privacy/terms/delete-account/support pages reflect actual implementation and FallSoft.Co policy.
- [ ] Create distinct app identifiers, keys/capabilities, subscriptions and one-month offers in existing company accounts.
- [ ] Sign release archive/AAB. Verify release build behavior, dependency notices, privacy manifests and resource shrinker rules.
- [ ] Sandbox purchase/renewal/refund/restore, push, external account callbacks, local downloads and real cross-platform messaging.
- [ ] Store screenshots, icon and truthful listing; reviewer instructions/account with complete usable access.
- [ ] Upload TestFlight/Play test builds; complete any account-specific testing prerequisites.
- [ ] Submit both apps for review and record exact version/build/submission states. Acceptance remains the stores' decision.

The user has authorized deployment and submission after proof. Ask only for missing access, concrete spending choices, or consequential product decisions that cannot be resolved from their instructions. Do not ask again merely because a step is deployment or submission.
