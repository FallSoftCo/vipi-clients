# Implementation sequence and release gates

For the current milestone, source checkpoint and open gates, read
[Current delivery status](DELIVERY_STATUS.md). The dated sections and original
checklist below preserve the implementation history; unchecked historical items
are not an authoritative description of the current code or qualification.

## Consolidated delivery work — 2026-11-07

The retained CPU source was recovered at `15339619ccce2d7492f5090906b1498b36d93928`, including all dirty tracked edits and 22 untracked source files. Canonical work continues in the reconciled delivery workspace; the retired CPU/GPU hosts are not development targets. The Apple team uses the existing development VM and Android reuses its existing QA emulator. A parent-owned delivery ledger records source authority, host receipts, platform results and remaining gates.

The backend candidate adds provider-verified base/Bot mini subscriptions, a bounded response-only bot gateway, selected-reply reports and a private APNs/FCM outbox. Ninety-seven checks passed against an isolated PostgreSQL 16.15 instance after migrations through `20261107_03`, including concurrent budget admission, account deletion, purchase replacement, uncertain provider responses and push-generation races. These tests use controlled provider responses; actual store transactions, DeepSeek responses and OS push delivery are still open. No candidate capability is advertised as live merely because configuration fields exist.

Selected full-app Apple conversation checks pass continuous flipping, stable geometry, Swahili, non-Roman readings and large text. Android checks exposed and fixed menu unmounting and cramped metadata, with repeated full-app controls passing after those changes. Native bot tests cover consent, private persistence, history bounds, uncertain requests and selected-only reports. These authored cases do not measure general language coverage or live friend delivery.

The frozen whole-reference comparison still fails its meaning-error gate: a stronger full translator improves whole-reference quality without improving clean mixed-language coverage. Reviewed source-only lookup is more promising for beginner exposure: 219 source forms across 158 concept groups plus guarded questions reach 69/80 clean useful messages on a new sample, versus 62 for the paired 100-entry control, without translation calls in that experiment. Content-only reach is 35/80. A further clause trial increases depth but not clean availability; Japanese transfer remains under review. Native packs remain unchanged. Partial source hits currently still trigger full translation, so the next routing comparison separates immediate source-unit selection from deferred whole translation. Fresh Apple translation preparation remains held below the observed 10-GiB OS purge threshold. See the current verification checkpoint for exact denominators and limits.

Delivery order remains: finish source/runtime fixes and comparative immersion evidence; prove authenticated native cross-platform encrypted chat and recovery; qualify actual store purchase lifecycles, bot processing, push and privacy disclosures; measure signed release package sizes; prepare corresponding source, store metadata and reviewer access; upload and submit only the qualified builds. Store acceptance requires actual receipts. Apple store sign-in and Google Cloud organization reauthentication currently need owner interaction; other work continues.

Latest bulk expansion and native run 018: [BULK_LANGUAGE_EXPANSION.md](BULK_LANGUAGE_EXPANSION.md). This is experimental language data; the default catalog remains bundle 022.

Latest qualified catalog: bundle 022. Android and physical iPad native catalog suites pass, including Swahili, all 110 directions, exact readings and finite attachments. Both language pickers pass twelve unfiltered physical iPad audits. Actual VoiceOver, speech listening quality, independent meaning accuracy and majority conversational coverage remain open.

Every gate needs a retained command/build/device receipt. A screenshot proves appearance, not encryption, billing or delivery correctness. No store submission until the release-blocking gates pass.

## Current verified state — 2026-10-27

Broad expansion now includes 1.586 GB of native dictionary shards and 300 MB
of contextual witnesses (1,447,899 rules). Android and physical iPad run 012
pass 15,342 diagnostic cases. Fresh reserved run 013 passes 8,410 reference
pairs across 102 directions: separate-path availability rises from 15.92% to
35.21% on Android and 16.18% to 35.67% on iPad. This is not an integrated app
result, majority conversation coverage or independent meaning acceptance.
The default remains bundle 022. See CONTEXT_WITNESS_QUALIFICATION.md.

Bundle 022 has 55,786 author-assessed records, 41,251 lexical units, 14,529 whole references and 423 exact readings. Latest Android catalog 021 passes seven tests; physical iPad 021 passes eight. Complete parity trace 004 agrees on all 14,529 authored references, with 14,986 identical selected spans. The prior full bundle 021 suites also pass. Short replies flip continuously with fixed geometry on both platforms, including both Swahili language roles on the physical iPad at AccessibilityXXXL. AfriWOZ availability is 52.70%; spontaneous Swahili remains 3.82% automatic / 7.91% explicitly selected. Seven-source replay availability is 18.08% SMS, 44.81% booking and 21.30% persona. The last two Korean–Chinese authored reference differences are resolved by explicit combined carriers. These are diagnostic availability results, not independent precision or majority conversational coverage. See the latest verification entry for exact versions, hashes and remaining limits.

Previous catalog checkpoint: bundle 015, 27,959 author-assessed records, 16,036 complete lexical units and 12,575 exact references across all 110 directions, including Swahili. Android catalog 013 and physical iPad 014 pass; all prior references remain unchanged. Both clients verify 410 exact whole-sentence readings. iPhone full chat 044 and physical iPad 009 each pass eleven tests; Android chat 010 passes three. New long-greeting wrapping is separately qualified on iPhone 046, iPad 011 and Android, with 110-direction layout matrices on both platforms. AfriWOZ availability rises to 693/2,410 cases; spontaneous Swahili remains 23 automatic / 50 explicit cases out of 1,910. Broad coverage, independent precision, VoiceOver interaction and speech listening acceptance remain open. The verification ledger records exact versions and does not equate authored catalog size with general-chat coverage.

The subsequent physical iPad full chat suite 012 passes twelve tests on bundle 015 (264.064s). Android chat 011 and actual TalkBack 012 pass, including hiding inactive switching controls and restoring them after the service stops. Physical VoiceOver remains unaccepted: direct service-state evidence invalidated a quiet-screen false positive. Settings/notification cleanup and closed device-control forwards are documented in VERIFICATION.md.

Bundle **012** is now qualified on both native platforms. The 32-noun expansion adds 8,320 explicitly assessed written-form units; the catalog has 8,980 complete units, 20,903 author-assessed records and unchanged 10,615 complete references. Android catalog 011 selects 10,782 spans; physical iPad 012 selects 10,798. Both verify 364 shared Latin spellings stay unchanged. Native comparison loses no previously supported messages and gains 24. iPhone chat 041 passes all ten tests; Android chat 009 passes both tests. AfriWOZ run 007 improves to 385/2,410 directed cases with immersion (16.0%); spontaneous Swahili run 003 reaches only 8 automatic or 24 explicit-Swahili cases out of 1,910. Neither result is an independent semantic score or majority coverage. The next time/social unit batch is still being qualified; a static audit withdrew 272 ambiguous source records before promotion. The 1,810-row AfriSenti training-only authoring queue is now reproducible, with no automatic dictionary promotion.

### Earlier checkpoint

Latest continuation, 16:30 Eastern: Swahili works in both native clients’ translation, speech, previews and conversation immersion. Bundle 010 has 10,615 authored references across 110 directions; native catalog 009 passes on Android and the physical iPad with 10,399 spans and 660 complete-compound cases. Explicit data repair restores eighty cases lost by the initial compound batch; native comparison shows zero lost and ten gained authored messages. iPhone chat suite 040 passes all ten tests with unfiltered appearance audits, four non-Roman whole readings at the largest text size, pace controls and Swahili onboarding. Android chat 007, readings 003 and actual TalkBack 010 pass. Both clients qualify 390 exact whole-sentence readings; unknown clauses abstain. **Useful broad coverage remains unachieved:** current bundle 010 still gives zero substitutions on the 191-turn spontaneous Swahili probe. The current booking-domain probe improves from 29 to 55/2,410 cases (2.282%), still far below majority coverage. Training data and reserved evaluation remain separate. Continue explicitly assessed vocabulary scope expansion and fresh native evaluation. VoiceOver, listening/recovery, current physical chat automation and release work remain open. See SWAHILI_AND_CHAT_IMMERSION.md and VERIFICATION.md; older experiment paragraphs below are historical.

The product remains under implementation. Active staging release `eca2badb86f802d7259554a866cbc446eb0619b4` uses Vipi's dedicated WorkOS pool and separate PostgreSQL DB. Messaging admits three controlled fixture IDs; two are live and the disposable web identity has been deleted. Any recently authenticated dedicated Vipi identity can erase itself, including before messaging admission. Both native clients passed another real public HTTPS encrypted exchange with refresh, out-of-order delivery, durable receipts and duplicate recovery. Manual encryption-key comparison is implemented with libsignal; cross-platform numbers, key-bound persistence and Android interactions passed. Final native presentation checks passed; external onboarding checks passed an isolated Android release build with production optimization rules. ARM and complete production flows remain open.

General conversation immersion is still gated. All 90 revision-007/schema-4 dictionary packs are built; actual SMS probes expose insufficient strict coverage and remaining sense/scope errors. Separately, 5,457 explicitly author-assessed contextual mappings now compile into 90 signed development packs and pass indexed native lookup/alignment on Android and the physical iPad, including complete sentences within longer messages. Their 61 new everyday meanings are authored development examples, not representative conversation coverage. No new release trust key was added. FTS retrieval, source-sense checks and native linguistic tags do not independently certify meaning. Prior E5, AWESOME, placeholder and catalog-consensus experiments remain rejected and unintegrated. The reused FLORES and 400-message SMS probes are diagnostic/regression material; untouched acceptance data and broader reading/meaning review remain required.

The latest source-evidence experiment retains 214,727 native Chinese forms independently of pivot translations. Both native clients enforce compound boundaries and unresolved native analyses under a new signed-pack policy that older clients reject. The 200-message Chinese→English replay withholds three known Android errors, while reducing availability to 32 messages on each platform; five known Chinese failures and whole-message translation errors remain. It is qualified as an experiment, not promoted or counted as increased conversation coverage. See the 2026-10-26 verification entry.

Physical iPad automation is now authorized. The corrected on-device preparation/translation test passed all 90 directions and 540 authored inputs on iPadOS 18.1.1, first online and then with every network-path observation unavailable. Physical continuous-flip, transliteration and audio UI tests also passed. Linguistic acceptance, cold-launch offline release behavior and general-chat immersion remain separate gates. App Store Connect requires renewed FallSoft sign-in and Account Holder agreement action. No Vipi store app, subscription product or submission has been created. Conversation reading, keyboard, explicit jump and variable-height older-page insertion now pass native emulator/simulator UI checks. That historical iOS audit failed with 23 findings; current chat suite 029 passes both unfiltered appearance audits and largest-text checks. Native account deletion and the backend workflow passed recovery/concurrency tests. The dedicated Vipi WorkOS project passed real provider deletion for complete and unfinished accounts, plus real hosted PKCE sign-in and a second password reauthentication. The public browser deletion route now passed actual sign-in, confirmation, persisted pending state and provider removal. Live testing caught and corrected the cleanup unit's missing HTTPS socket permission; the pending job recovered automatically. Complete native new-account/reauthentication UI flows still need qualification. Production billing, bot, push/relay, replacement/revocation, reporting, backups, language distribution, load and release-policy checks remain open.

## Current priority — user directive, 2026-10-24

2026-10-25 continuation after the Mac returned: actual local translation and signed native lookup now cover separate 3,600-case English/Chinese SMS, 3,600-case Arabic/French Multi3WOZ and 2,700-case Italian/Japanese/Korean XPersona probes on both platforms. These are seven conversational source languages, not ten-language acceptance. XPersona official test files remain uninspected. The ledger has 140,062 current records: 7,077 author-assessed (5,457 exact contexts plus 1,620 phrase frames), 18 quarantined and 132,967 candidates. The phrase packs now cover 18 constructions across all 90 directions. Both platforms pass all 1,620 reference mappings; actual-output replay produces immersion in 964 Android and 1,109 iPad authored cases. Incremental captures preserve exact unchanged-case provenance and make fresh calls for new or corrected cases. A French authoring error was quarantined and corrected, not counted as a valid linguistic pass.

On XPersona, the phrase expansion adds 20 Android and 19 iPad cases beyond generic dictionaries. Separate-path union availability is 20.67% and 22.44%, with all gains from four Italian source messages. This is still far below majority coverage and is neither an accuracy estimate nor integrated general-chat behavior. Original SMS/Multi3WOZ sense and scope failures and whole-message provider errors remain open. Tatoeba supplies 20,296 direct-link candidates; NUS and nine UD corpora provide frequency/grammar priorities. The 124.5 MB observed-form index retains 254,994 analyses; its plural-noun supplement added no strict coverage and remains unpromoted. Next work must broaden contextual concepts and languages while reducing grammar/compound/sense errors, then evaluate untouched material. See CONVERSATION_COVERAGE.md, PHRASE_FRAME_QUALIFICATION.md and VERIFICATION.md for exact evidence and limits.

Latest incremental checks: revision-006 Android replay selects 162 spans in 122/540 messages with 22 empty directions; physical iPad replay selects 148 spans in 118/540 with 23 empty directions. The relaxed all-senses shared-surface probe failed inspection and is rejected. Physical FTS qualification now passes 54 attested-example queries across 18 directions; this is index execution evidence, not general sentence understanding. Expand precomputed contextual mappings and retain usage/phrase constraints before integrating them with chat. iOS Settings exposes native translation-model preparation; five lifecycle cases and light/dark navigation tests pass. Physical production download consent remains unqualified. Android rejects stale sample translations and withholds output whose protected literals cannot be verified; that literal check does not certify meaning. Physical timeline run 001 encountered a renewed XCTest passcode challenge before executing methods, and the owner has been asked to complete it. Native unit tests continue to run on the iPad. See VERIFICATION.md for exact evidence and limits.

Demonstrate the core immersion UX across at least ten major languages and every directed pair, including transliteration for non-Roman scripts. Initial qualification set: English, Spanish, French, German, Italian, Portuguese, Arabic, Mandarin Chinese, Japanese and Korean. This is 90 directions per platform, 180 platform/direction combinations. Do not substitute a download/availability check, English-only pivot example or isolated welcome screenshot for this proof. See IMMERSION_ACCEPTANCE.md. Infrastructure work already started is retained, but broader deployment and store work follow this gate.

### Current language UX implementation

- [x] Continuous native vocabulary alternation, optional immediate reveal, pause, three pace settings, and a single full-translation reading surface.
- [x] Eleven-language authored previews including Swahili, with mandatory readings for Arabic, Chinese, Japanese and Korean; native layout qualification across all 110 directions.
- [x] Native selection/copy and fixed inline vocabulary blocks with subtle backgrounds and minimal rounding; glyph-position checks across three widths and three text sizes. This does not establish full conversation layout or human usability.
- [x] Native preview speech/reading interaction checks on both clients, including a fixed visible snapshot during audio.
- [x] Physical preview interaction: continuous flip/pause, Japanese transliteration/script/full thought, audio snapshot and cancellation. Four iPad UI tests passed.
- [x] Actual Android TalkBack, including native word actions and a long-message chooser.
- [ ] Actual VoiceOver and broader acoustic/comprehension qualification.
- [x] Actual Apple local translation on the user's iPad with networking unavailable: 90 directions, 540 samples. The development-signed app was launched online before disconnecting; this does not qualify a cold offline release launch.
- [ ] Production multilingual pack compilation, contextual reading generation and held-out meaning/coverage evaluation.
- [x] Real conversation component integration, cancellation/language-change lifecycle, composition pause, full translation and simulator light/dark accessibility checks. Synthetic transport is explicit.
- [x] Incoming learning-language normalization, per-message language override, immutable copy original and long-history immersion scrolling in native qualification.
- [x] Exact whole-sentence Latin readings for 423 authored Arabic/Chinese/Japanese/Korean references; unknown sentences still abstain.
- [ ] Complete voice recovery/listening acceptance and physical VoiceOver interaction; the physical chat suite and earlier-page insertion now pass.

## Historical store readiness review — 2026-10-24

The app is not at the submission stage. Language previews and local component tests must not be described as a complete messaging product. The paired iPad has a signed build and has passed eight physical component tests. Interactive Mac signing succeeded without changing keychain permissions. The owner completed XCTest authorization on 2026-10-25. Physical UI automation, the offline Apple translation matrix and four preview interaction tests now pass; actual conversation immersion and linguistic acceptance remain open.

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

Both clients now have encrypted conversation indexes, persistent compose drafts, unread state, keyset pagination and durable receipt retries. Native coordinators connect real username lookup, profile/device provisioning, session establishment, outbox submission and receiving to the service. Actual username lookup, compose, send, receive and delivered-state screens passed cross-platform UI/application qualification through public HTTPS. Foreground/lifecycle/send/explicit-refresh synchronization is implemented; contentless relay events, push and background retry are still required before live chat acceptance. Friend message text currently displays the original while general contextual immersion remains gated on linguistic quality. Native 70-message timeline checks now pass for append/keyboard reading-position preservation, explicit sends and jumping/following latest. Variable-height older-page insertion now passes too. Actual largest-text scaling and bottom placement pass on iOS; its full automatic accessibility audit still fails, and physical accessibility remains open.

Design references reviewed through MCP: [WhatsApp starting a chat](https://mobbin.com/flows/83ca5b13-659e-4eb1-952b-cc340bea3ab3), [WhatsApp chats](https://mobbin.com/flows/61481c3e-e374-49a2-ab2b-77c364d916e1), [Built for Mars reassurance about saved work](https://builtformars.com/ux-bites/reassuring-reload-message). Application: keep one clear first-chat action, place delivery status beside the message, and state that a failed connection does not discard a committed draft. BFM's analysis endpoint failed twice; content lookup and exact article retrieval succeeded. No reference UI/assets are copied into the product.

### Current release work still open after actual chat qualification

The current public endpoint remains restricted to two controlled staging users. The product is not ready for a store submission. Prioritize:

1. Broader conversation availability and independent meaning assessment remain unachieved. Swahili is implemented in both native clients, with eleven-language selection, 110 directions, offline translation/speech and explicit locally assessed mappings. Bundle 021 reaches 52.70% on the Swahili booking diagnostic but only 3.82% automatic / 7.91% explicit availability on the small spontaneous sample. These are availability figures, not accuracy or representative worldwide coverage.
2. Native continuous conversation immersion, fixed highlighted blocks, same-bubble full views, composing/selection/audio pauses and installed-language management now pass substantial Android and physical iPad qualification. Finish actual VoiceOver interaction, listening quality/recovery, broad meaning/readings acceptance and production pack signing/distribution. Exact native cross-platform parity now passes all 14,529 authored references; this does not replace independent meaning review.
3. Integrate ejabberd events, APNs/FCM and bounded foreground/background outbox scheduling. Exercise reconnect, poison envelopes, queue pagination, receipt responses after server metadata cleanup and terminal errors that must not block unrelated messages. No always-on polling launch.
4. Finish visible device replacement/safety-number/revocation behavior, account/profile editing, block/report/delete operations and user-controlled encrypted export/restore. Complete fresh-account onboarding and interruption/recovery UI proof.
5. Configure the confirmed company store accounts, products/trials, verified purchase state and refund/restore handling; implement and qualify vBot consent, provider streaming and spend controls. Google Play's Fallible Software, Co. organization is confirmed through one@fallsoft.co (developer 4750854689150545006). App Store Connect showed Fallible Software, Co., then required renewed sign-in for arjun@fallsoft.co before app creation. Apple also flags an updated Paid Applications Schedule for the Account Holder. No Vipi app record or product has been created yet.
6. Product-specific public policies, corresponding-source/dependency release, load/recovery/security checks, physical notification/lifecycle proof, signed release builds, truthful store assets and submission.

The unlocked iPad passed eight physical component tests, including mixed speech and durable Signal/storage checks. Autonomous developer screenshots and accessibility inspection now work through the Mac's paired USB connection. The physical screen proves a separate passcode challenge: “Enter iPad Passcode for ‘XCTest’ — Enable UI Automation.” The Developer setting is already on; ordinary unlocking does not satisfy this session challenge. Runs 002/003 stop before test methods. Accessibility activation did not start Apple's model download, and this iPadOS version does not expose the newer CoreDevice touch service. No model-preparation completion or physical UI pass is claimed. The temporary private USB forwards are closed; no repeated prompt loop remains active. This historical authorization blocker was resolved by the owner on 2026-10-25. The subsequent automated download/translation test passed; current proof and limits are in the verification ledger.
