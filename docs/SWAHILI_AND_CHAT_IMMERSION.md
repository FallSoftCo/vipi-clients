# Swahili and conversation immersion

Updated 2026-10-26, 13:20 Eastern. Native conversation immersion is substantially implemented. Vipi is not store-ready, has not been submitted, and has no demonstrated majority conversational coverage.

## Current behavior

- Eleven languages, including Swahili (sw, Kiswahili), in both native pickers and onboarding previews: 110 directed pairs.
- Continuous inline vocabulary alternation in actual conversation components, fixed highlighted gaps, source grammar outside scoped vocabulary, and whole-language views replacing the same bubble.
- English and Swahili originals both work with an English-known/Swahili-learning pair. Incoming learning-language text is translated locally into the known-language reading baseline. The sender's original remains the copy, transport and encrypted-storage text. Reading-menu labels name the languages.
- Bundled local language identification precedes unknown-input translation. The strongest result must have confidence at least 0.85 and the runner-up at most 0.10. Fewer than four letters, unidentified languages and romanized-language tags abstain. Exact forward/reverse references work without models. A per-message override selects either language in the pair. This is whole-string identification, not arbitrary code-switch segmentation.
- Serial per-conversation work, cancellation/epoch invalidation, bounded 128-result transient cache and explicit model preparation. Recycled rows initialize from existing cached results, fixing a measured 19-pixel transient layout shift during earlier-page insertion.
- Switching pauses during drafting, scrolling, selection, playback, background/offscreen state and screen-reader use. An emptied composer resumes switching after Send. Mounting another row cannot stop active speech.
- Both voices prepare on conversation entry. Mixed-language speech uses one PCM playback where synthesis succeeds. Missing voices have setup/retry actions; recovery surfaces scroll at large text sizes. Speech receives native text, never a Latin reading masquerading as native speech.

Swift and Kotlin implementations remain separate. [ML Kit language identification](https://developers.google.com/ml-kit/language/identification/ios) is pinned as GoogleMLKit/LanguageID 8.0.0 on iOS and language-id:17.0.6 on Android. The eleven authored classifier paragraphs are execution samples, not independent accuracy evaluation.

## Swahili translation and speech

The attached iPad runs iPadOS 18.1.1. Its measured Apple Translation languages exclude Swahili, and its installed AVSpeech voices have no Swahili voice. Physical iOS therefore uses GoogleMLKit/Translate 8.0.0 for Swahili pairs; other initial pairs retain Apple Translation. Downloads are explicit and removable. A translation request never starts a model download.

Physical test ipad-swahili-006 executed all twenty Swahili translation directions with networking available. Execution is not semantic approval. Raw English “I am drinking water now.” produced the incorrect “Mimi ni kunywa maji sasa.” Exact authored-reference lookup gives “Ninakunywa maji sasa.” A changed person or tense cannot borrow that complete reference.

Android uses ML Kit and the installed Google offline voice sw-ke-language. Test swahili-android-native-002 passed actual translation and synthesis with emulator Wi-Fi/mobile data disabled, then restored. It produced 3,950 ms of 24 kHz audio. Other Android devices must have a suitable offline voice installed; no embedded Android fallback is claimed.

Physical iOS speech uses eSpeak NG Swift pinned to fd28f6460cc4cdf631528c8e2f7bd825747aac5c. Its process-global engine is confined to one queue, input is literal UTF-8 without SSML, and cancellation is thread-safe. First preparation took 6,509 ms. A mixed render took 58 ms and produced 1,901 ms of mono 24 kHz PCM; a separate Swahili sentence produced 4,841 ms. This is a synthetic/formant voice. Listening quality has not been accepted. Notices are present; corresponding-source and distribution review remain release gates.

## Live authored catalog

The incremental ledger has 142,057 revisions, 141,598 current records, 8,613 author-assessed records (6,633 contexts and 1,980 frames), eighteen quarantined records and 132,967 candidates. Sixteen imports are complete through sequence 151444. Author assessment is distinct from independent linguistic acceptance.

Swahili additions comprise eighteen constructions/360 frame mappings and 59 everyday topics/1,176 exact context mappings across twenty directions. Finite person/tense prefixes and possessors are explicit; no arbitrary stemmer is inferred. Native locative suffixes remain outside the focus in “Niko ofisini” and “Niko nyumbani.” Discontinuous ownership and known Chinese/Arabic ambiguities are excluded. Content-bound assessments are in qa/immersion/swahili_frame_author_assessment_001.json and swahili_context_author_assessment_001.json.

Bundle 004 contains 110 frame plus 110 context databases, 46,301,184 SQLite bytes and 8,393 consistent complete references. Twenty conflicts are omitted. Both native catalog tests select 8,243 spans and reconstruct originals when meanings are revealed. Independently known complete sentences can compose while preserving whitespace; unknown clauses prevent that shortcut. Catalog SHA: 6eedd0b7d04fa82c905c648f35824d747ac87c9da6945f3caf4a1799ed0fb20a.

App signing authenticates public assets; runtime checks database hashes. Qualification keys and private messages are absent. The index retains release_ready:false. Later downloadable updates use the separate signed-pack installer.

## Full-sentence transliteration

authored_sentence_readings.py adds 307 explicit Latin readings: 76 Arabic and 77 each Chinese, Japanese and Korean. Exact catalog and authoring hashes bind the source sentences. Generated asset: 29,447 bytes, SHA 3294a55d9928824abcce2b2fba5be4dea22febd6bff1e2722a406bde2fa8d5cd.

Both native readers preserve paragraph whitespace, add a Latin sentence separator where adjacent Japanese/Chinese sentences need one, and abstain on changed sentences or unknown clauses. Whole translated views can switch between the reading and original script in place. Audio retains the native sentence. Unsupported whole readings no longer expose a nonfunctional script-toggle action. Every non-Roman lexical substitution still requires its own explicit reading.

These are practical authored readings, not IPA or pronunciation certification. [National Institute of Korean Language guidance](https://www.korean.go.kr/front_eng/roman/roman_01.do) informed review: the first draft's “ilkgo” was corrected to “ilgo” before app promotion. Unknown sentences do not receive fabricated readings. Audio remains the pronunciation path.

## Qualification receipts

| Check | Result and scope |
| --- | --- |
| Android bundled catalog 003 | Pass: 8,393 references/110 directions, 24.971s |
| Physical iPad bundled catalog 003 | Pass: same references/spans, 24.823s |
| Native fixed-block preview matrix | Pass: 110 directions per platform, three widths/fonts/faces; Android 11.863s, iPad 72.827s |
| Android message language 001 | Two tests pass: eleven authored classifier paragraphs, reverse reference and actual unseen Swahili reverse translation |
| Physical iPad lifecycle 004 | Ten tests pass: classifier/reverse paths, stale/cancelled replies and download races; 0.419s |
| Android chat 005 | Two tests pass: both original-language directions, manual override, copy original, switching, fixed height and draft pause; 43.507s |
| Android immersed history 004 | Pass: seventy-message append/keyboard/send/jump/earlier-page behavior; 14.163s |
| Android speech 001 | Actual playback survives another row mounting; 6.832s |
| Android TalkBack 006 | Actual TalkBack service: eight-second automatic pause, readable visible text, native word action, automatic resume and settings restoration; 18.670s |
| Physical iPad sentence readings 001 | Pass: all 307 readings, paragraphs and unknown-clause abstention; 0.138s |
| Android sentence readings 001 | Two tests pass: catalog plus Japanese chat reading/script/native-language controls; 8.254s |
| iPhone simulator chat 021 | Six of eight tests pass. The two failing audit tests report light-theme contrast; the earlier Dynamic Type findings are absent. Japanese full readings, language-settings return, seventy-message history, largest-size metadata/status details, switching/send and reverse input/copy pass. |
| iPhone targeted audit 022–024 | Light-theme contrast still fails after clearer Send styling and stronger secondary text. Dark appearance passes. Diagnostic isolation is in progress; these are not acceptance passes. |

Android history failures exposed both a real cache-related 19-pixel shift and test queries assuming plain Text after native immersion replaced it. Stable message identities now anchor those checks. One failed run installed an older test APK before its rebuild completed; it is not credited to the fix.

The iPhone audit began with fourteen findings, briefly passed in 012, regressed to eight in 013–016, and retained two Dynamic Type findings in 019–020. Compact language/status controls with a scrollable status sheet replace pinned explanatory paragraphs; largest-text tests now require more than half the display for the timeline. Metadata still scales and wraps without a font cap. Suite 021 no longer reports Dynamic Type findings, but a light-theme contrast finding remains through 024. No acceptance audit filters issues. A temporary, explicitly non-acceptance diagnostic localizes that finding and restores its source edits afterward.

Actual TalkBack qualification exposed missing native actions: Compose semantics on AndroidView did not reach TextView's accessibility node. Actions now register directly on the native view. The first 31 words have individual actions; longer messages additionally expose a chooser containing every word. Run 006 proves the ordinary word action with the actual service, not a simulated accessibility flag. The chooser still needs its own interaction check. Earlier failures include test setup quoting, a delayed system notification prompt and a fixture initially positioned under the status bar; all are retained. The service and three accessibility settings returned to their initial values. No acoustic listening acceptance follows from this test.

Physical iPad UI automation still times out enabling XCTest mode. Native unit tests work. The user has been asked to check the device confirmation. No physical chat UI pass or authentication bypass is claimed. The dedicated simulator scheme explicitly reports ML Kit unavailable because its SDK has no arm64 simulator slice; it does not fake model execution.

## Conversation coverage and continuous expansion

The authors' [AfriWOZ repository](https://github.com/masakhane-io/chatbots-african-languages), pinned at 3961ae0c514bb019598a9b042da21b3a586bc090, supplies a separate Swahili task-oriented probe. Data is CC-BY 4.0, distinct from repository code's MIT license. The training workbook has 999 nonempty turns. Published 250 test turns yield 241 after eight development duplicates and one test duplicate are excluded.

Frozen corpus SHA: 3886fca840451c66767748a6afdd1a317d1dba917e89c9bf4d9bc56842c54ba0. Both platforms completed all 2,410 cases with the pre-expansion catalog. **Both selected zero substitutions.** A whole translation alone is not useful immersion coverage. One iPad Chinese output failed identifier preservation. Median/p95 translation-plus-lookup times were 139.929/277.273 ms Android and 22.502/48.705 ms iPad. Raw report hashes: 775cb7e1da2dd22ac6b8d324aecccf7a5b7c6b659c52eb5b5aaa7e068b92226a and a56c75298662ec79dc4cdcb300918c662b5f21495b4fa3391a553049de252724. No held-out messages supplied new authoring, and no coverage gain is inferred from additions. This booking-domain corpus does not represent all friend conversations.

The new Swahili dictionary index scans all 11,121,531 entries in the pinned upstream extraction. It retains 20,557 native headwords, 24,424 senses, 300,829 recorded forms and explicit direct translation candidates for 5,267 English headwords. Shared-sense links remain labelled pivot evidence; forms do not imply general morphology. Index: 104,243,200 bytes, SHA 46395c3ed74c76ec55e2006c9ea665b4e2a11384877dd3fb264d8a32297cdbae; scan/build 417.19s. CC-BY-SA 4.0 attribution, source URLs/lines, glosses and tags remain. This unqualified research schema is not installed in either app. The incremental revision/review/export ledger remains the promotion path.

Generic packs with known meaning failures remain unpromoted. Open gates include independent meaning/coverage evaluation, VoiceOver and long-message TalkBack interaction, speech listening/recovery acceptance, physical chat UI, cold offline release behavior and the remaining store/security/billing/backend checks.

The main gallery category is vipi-swahili-chat-20261026; its initial published captures are historical and await updated reviewed images. Mobbin Messages/Bolt examples informed compact controls. Built for Mars supported context-local correction but cited only indirect examples; this is design input, not usability validation.
