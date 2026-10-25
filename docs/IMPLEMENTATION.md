# Implementation sequence and release gates

Every gate needs a retained command/build/device receipt. A screenshot proves appearance, not encryption, billing or delivery correctness. No store submission until the release-blocking gates pass.

## Current verified state — 2026-10-25

The product remains under implementation. The staging API is restricted to two controlled accounts; active release `1fd2e8c3f638a5a0b8698e7b87b4a34d26797503` includes durable recovery and blocking. Both native clients have real encrypted HTTP chat and durable local history. Manual encryption-key comparison is implemented with libsignal; cross-platform numbers, key-bound persistence and Android interactions passed. Final native presentation checks passed; external onboarding checks passed an isolated Android release build with production optimization rules. ARM and complete production flows remain open.

General conversation immersion is still gated. Revision-005 packs cover all 90 directions, but contextual meaning is not accepted. The stricter sentence-cue policy suppresses all replacements in 22 directions in the six-example chat sample on each platform. The E5 dictionary-gloss pilot failed its predeclared English probe. A separate contextual token-alignment pilot selected 325/360 easy authored correspondences with five wrong matches; it also remains unaccepted and unintegrated. The reused FLORES sample is now a regression corpus; untouched acceptance data and broader reading/meaning review remain required.

Physical iPad component checks passed, but Apple's separate XCTest passcode authorization still prevents physical UI automation and Apple model-download/translation proof. App Store Connect requires renewed FallSoft sign-in and Account Holder agreement action. No Vipi store app, subscription product or submission has been created. Native account deletion and the backend workflow passed synthetic recovery/concurrency tests. WorkOS user isolation required a separate Vipi project, now created with free staging only; live provider lifecycle, cutover and the web deletion route remain open. Production billing, bot, push/relay, replacement/revocation, reporting, backups, language distribution, load and release-policy checks remain open.

## Current priority — user directive, 2026-10-24

Demonstrate the core immersion UX across at least ten major languages and every directed pair, including transliteration for non-Roman scripts. Initial qualification set: English, Spanish, French, German, Italian, Portuguese, Arabic, Mandarin Chinese, Japanese and Korean. This is 90 directions per platform, 180 platform/direction combinations. Do not substitute a download/availability check, English-only pivot example or isolated welcome screenshot for this proof. See IMMERSION_ACCEPTANCE.md. Infrastructure work already started is retained, but broader deployment and store work follow this gate.

### Current language UX implementation

- [x] Continuous native vocabulary alternation, optional immediate reveal, pause, three pace settings, and a single full-translation reading surface.
- [x] Ten-language authored previews with mandatory readings for Arabic, Chinese, Japanese and Korean; native tokenization and paragraph component coverage for all 90 directions.
- [x] Native selection/copy and fixed inline vocabulary blocks with subtle backgrounds and minimal rounding; glyph-position checks across three widths and three text sizes. This does not establish full conversation layout or human usability.
- [x] Native preview speech/reading interaction checks on both clients, including a fixed visible snapshot during audio.
- [ ] Physical speech/reading and actual VoiceOver/TalkBack qualification.
- [ ] Actual Apple local translation on the user's iPad; paired-device access and signing passed, but the separate XCTest passcode authorization remains pending.
- [ ] Production multilingual pack compilation, contextual reading generation and held-out meaning/coverage evaluation.
- [ ] Real conversation integration, lifecycle/accessibility/composer and scrolling qualification beyond the previews.

## Store readiness review — 2026-10-24

The app is not at the submission stage. Language previews and local component tests must not be described as a complete messaging product. The paired iPad has a signed build and has passed eight physical component tests. Interactive Mac signing succeeded without changing keychain permissions. The Developer automation setting is already enabled; the observed remaining barrier is the iPad passcode prompt for XCTest. Ordinary unlocking does not satisfy that separate authorization.

Work that can proceed without the unlocked iPad, in dependency order:

1. Durable encrypted native protocol stores and message journals, then prekey delivery, real transport, receipt/outbox workers and the conversation UI. Prove restart, rollback, duplicate, out-of-order, identity replacement and fixed expiry behavior before networking.
2. Production multilingual pack compilation, download/remove state and context/meaning evaluation. The 90-pair authored renderer preview is not this gate.
3. Native account session refresh, device binding, usernames/invites, account deletion and blocking/reporting. Test revoked sessions and interrupted onboarding.
4. Store product configuration and native purchase/restore flows, verified server entitlements, Bot mini consent/gateway/spend limits, encrypted export/restore.
5. Isolated backend deployment, DNS/TLS, push, operational recovery/load testing, public product policies and corresponding open-source client releases.
6. Signed release archives/AABs, store declarations/listings, release-build and sandbox checks, physical translation/speech/background verification, then submission.

The current official [Apple review guidelines](https://developer.apple.com/app-store/review/guidelines/) require a complete reviewable app, appropriate purchase disclosures, account deletion for account-creating apps, and safeguards for user-generated content. [Google's deletion requirements](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en) include both an in-app path and a functional web deletion route. Its [UGC policy](https://support.google.com/googleplay/android-developer/answer/9876937?hl=en) specifically requires blocking for direct messaging and appropriate reporting/moderation. No dedicated customer-support team is assumed, but abuse-report handling and developer contact still need a real operational route; a decorative report button is insufficient.

Recovery design review: [Mobbin's Family flow](https://mobbin.com/flows/58bd7e53-29ee-4448-9b60-7bafcc5b2b0a) visibly places its failure label and retry control beside the affected message. [BFM's eBay example](https://builtformars.com/ux-bites/messaging-on-ebay) supports contextual warnings, not claims about cryptographic recovery. Keep errors beside the message; distinguish accepted from delivered and delivered from read. Retain automatic retries inside the original deadline. Reject the advisory suggestion to require confirmation modals for every retry; after expiry, an explicitly labelled resend creates a new message. Account sign-in alone cannot recover message keys.

## 1. Foundations and decisions

- [x] Record product, architecture, data boundaries and release sequence.
- [x] Verify OZZZ-OS Android tools, Mac Xcode/simulators and company signing identity exist.
- [x] Renew AWS CLI and verify Route 53 domains/DNS access.
- [x] Select inexpensive AWS domain with registration AND renewal cost: mambovipi.app, AWS registration successful.
- [x] Choose host after capacity/workload inspection and ownership registration: isolated restricted staging on `ozzz-app`.
- [x] Pin and prove official libsignal 0.105.0 native interoperability; add AGPL-3.0-only client LICENSE/NOTICE under the user’s open-source approval. Complete release dependency notices and corresponding-source distribution remain required.
- [ ] Record build mirrors, dependency pins, reproducible commands and credentials inventory (locations only).

## 2. Prove the hard paths

- [ ] Native iOS <-> Android E2EE through a private ejabberd test instance: initial keys, first message, ratchet, offline reply, replay, wrong key, tamper, device replacement.
- [ ] Durable delivery receipt, crash recovery, deduplication and immutable 72-hour deadline with controllable clock tests.
- [ ] Whole-message local translation on both platforms, network-disabled after download.
- [ ] Contextual alignment benchmark, with measured precision/coverage and explicit abstentions, not just a canned demo.
- [ ] Mixed-language and full-language speech using local voices on each platform.
- [ ] Store trial/purchase and WorkOS native redirect feasibility in the actual accounts/environments.

### Durable messaging foundation now implemented

- [x] Native encrypted SQLite records, device-bound wrapping keys, backup exclusion and fail-closed missing-key handling.
- [x] Durable libsignal callbacks with transactional session/prekey updates and changed-identity rejection.
- [x] Persist outgoing drafts before encryption; atomically persist ciphertext with the ratchet. Identical retries reuse ciphertext.
- [x] Bind encrypted message metadata; persist incoming text/deduplication before acknowledging.
- [x] Prove transaction rollback, concurrent writers, cross-platform exchange through fixture transport, out-of-order replies, corruption rejection and abrupt process termination.
- [ ] Connect the foundation to prekey distribution, the real relay, background workers, identity replacement, backup/restore and conversation UI. Fixture transport is not a real messaging launch.

### Native HTTP path now qualified

- [x] Public-only prekey directory with bounded pools, monotonic publication revisions/IDs, atomic one-time allocation, exact claim retries, block/replacement enforcement and no classical-only downgrade on exhaustion.
- [x] Native private-key generation and durable pending publication; official libsignal verifies signatures before establishing a session. Replaying the same claim cannot reset a ratchet.
- [x] Account-bound HTTPS service clients and serialized WorkOS public-client refresh. Actual expired-token recovery passed on both native platforms; no client secret ships in either app.
- [x] Real iOS → API/PostgreSQL → Android encrypted delivery, three Android replies received out of order on iOS, vault reopening, route-tamper rejection, application receipts and duplicate sends after delivery. All four server ciphertexts were cleared after receipts.
- [x] Restricted staging deployment with public TLS, isolated database/account, expiry timer, certificate renewal rehearsal and real public HTTPS native exchange.
- [ ] ejabberd event/relay integration, push, reconnect/background scheduling, transport load testing, immediate session revocation, prekey retirement and identity-change UI. The live service admits only controlled QA accounts.
- [x] Connect and qualify the messaging core through actual username lookup, chat list, composer and conversation screens on both platforms. Profile/device onboarding is implemented; its complete new-account UI path and replacement/recovery still require qualification.

## 3. Native product

- [ ] Design tokens, native theme preference, accessibility foundation and routing.
- [ ] Welcome/interactive immersion preview, language selection, download state, authentication, username, trial, first-chat onboarding.
- [ ] Real chat list, compose/invite/exact lookup, friend conversation, vBot conversation.
- [ ] Local persistence/outbox, timestamps, delivery states, unread/navigation restoration, paging and keyboard behavior.
- [ ] Original/mixed/full translation in-place rendering, automatic vocabulary flip-flop, optional contextual reveal/hold, copy, selection and speech. Prove a no-tap comprehension path; timer changes must preserve layout and pause during reading interactions/audio.
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

### Current native conversation integration

Both clients now have encrypted conversation indexes, persistent compose drafts, unread state, keyset pagination and durable receipt retries. Native coordinators connect real username lookup, profile/device provisioning, session establishment, outbox submission and receiving to the service. Actual username lookup, compose, send, receive and delivered-state screens passed cross-platform UI/application qualification through public HTTPS. Foreground/lifecycle/send/explicit-refresh synchronization is implemented; contentless relay events, push and background retry are still required before live chat acceptance. Friend message text currently displays the original while general contextual immersion remains gated on linguistic quality.

Design references reviewed through MCP: [WhatsApp starting a chat](https://mobbin.com/flows/83ca5b13-659e-4eb1-952b-cc340bea3ab3), [WhatsApp chats](https://mobbin.com/flows/61481c3e-e374-49a2-ab2b-77c364d916e1), [Built for Mars reassurance about saved work](https://builtformars.com/ux-bites/reassuring-reload-message). Application: keep one clear first-chat action, place delivery status beside the message, and state that a failed connection does not discard a committed draft. BFM's analysis endpoint failed twice; content lookup and exact article retrieval succeeded. No reference UI/assets are copied into the product.

### Release work still open after actual chat qualification

The current public endpoint remains restricted to two controlled staging users. The product is not ready for a store submission. Prioritize:

1. Prove the physical Apple model-download/translation path and offline execution; assess actual translation, contextual replacement and reading errors for all 90 directions. The new sense catalog measures candidate coverage only.
2. Export and qualify downloadable language packs, connect them to real conversation text, and verify continuous immersion/audio during scrolling, typing, navigation and accessibility use. Native unspaced-script dictionary lookup is now qualified independently.
3. Integrate ejabberd events, APNs/FCM and bounded foreground/background outbox scheduling. Exercise reconnect, poison envelopes, queue pagination, receipt responses after server metadata cleanup and terminal errors that must not block unrelated messages. No always-on polling launch.
4. Finish visible device replacement/safety-number/revocation behavior, account/profile editing, block/report/delete operations and user-controlled encrypted export/restore. Complete fresh-account onboarding and interruption/recovery UI proof.
5. Configure the confirmed company store accounts, products/trials, verified purchase state and refund/restore handling; implement and qualify vBot consent, provider streaming and spend controls. Google Play's Fallible Software, Co. organization is confirmed through one@fallsoft.co (developer 4750854689150545006). App Store Connect showed Fallible Software, Co., then required renewed sign-in for arjun@fallsoft.co before app creation. Apple also flags an updated Paid Applications Schedule for the Account Holder. No Vipi app record or product has been created yet.
6. Product-specific public policies, corresponding-source/dependency release, load/recovery/security checks, physical notification/lifecycle proof, signed release builds, truthful store assets and submission.

The unlocked iPad passed eight physical component tests, including mixed speech and durable Signal/storage checks. Autonomous developer screenshots and accessibility inspection now work through the Mac's paired USB connection. The physical screen proves a separate passcode challenge: “Enter iPad Passcode for ‘XCTest’ — Enable UI Automation.” The Developer setting is already on; ordinary unlocking does not satisfy this session challenge. Runs 002/003 stop before test methods. Accessibility activation did not start Apple's model download, and this iPadOS version does not expose the newer CoreDevice touch service. No model-preparation completion or physical UI pass is claimed. The temporary private USB forwards are closed; no repeated prompt loop remains active. Resume physical UI testing after the owner completes the device's authentication, without asking them to tap every download.
