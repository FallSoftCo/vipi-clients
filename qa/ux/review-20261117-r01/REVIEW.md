# Vipi UI and UX review — 2026-11-17

Status: in progress. Reference research and source review are complete enough to guide fixes; current native screen and interaction qualification is still running. This report does not certify “world class,” language accuracy, or store readiness.

## Evidence rules

Record the source revision, installed artifact hash, platform/device, locale, theme and text size for each capture. A still establishes only the visible layout and wording. Playback, continuous switching, keyboard handling, recovery and subscription expiry require observed interactions or focused native checks. Earlier screenshots remain useful baselines, not evidence for a changed build.

Native owners keep source changes isolated until their actual candidates are qualified. No repeated signing, upload, purchase, test notification or external message is required by this review.

## Reference comparisons

| Reference inspected through MCP | Application to Vipi | Limit |
| --- | --- | --- |
| [Mobbin: WhatsApp invite](https://mobbin.com/flows/cce40094-5111-4ee4-a7f5-90737cda749a?tab=screens) | Clear share-invite action, with the user choosing the recipient in the native share sheet. | iOS reference; not Android-specific evidence. |
| [Mobbin: Signal empty chat and group creation](https://mobbin.com/flows/a9c2cf2f-20b9-428d-8f31-c0cafe09a77d?tab=screens) | Empty state explains the next action and exposes compose. | Vipi must also explain why ordinary friend conversations teach words. |
| [Mobbin: Speak audio](https://mobbin.com/flows/1a1c0daf-879b-42f3-8100-9e03af3705f7?tab=screens) | Playback has distinct preparing, playing and stop states in a stable location. | Does not prove Vipi voice readiness or pronunciation. |
| [Mobbin: Glovo translation](https://mobbin.com/flows/50aecc0a-c9ce-49bd-b4ae-41f9a1f3857a?tab=screens) | Keep chat geometry familiar and make translation state understandable. | Vipi’s automatic inline switching needs its own interaction validation. |
| [Mobbin: Tide Guide subscription](https://mobbin.com/flows/5bef40b5-8760-4eb3-b232-dfaf5da7b41b?tab=screens) | Separate current access, renewal date and subscription management. | Its offer is not Vipi’s cardless access period. |
| [BFM: context and feature onboarding](https://builtformars.com/ux-bites/context-feature-onboarding) | Teach a control when it becomes useful, beside the actual example or chat. | A pattern recommendation, not measured Vipi adoption evidence. |
| [BFM: Signal account creation](https://builtformars.com/case-studies/creating-a-signal-account) | Ask for permissions in context; explain validation errors and the next recovery action. | Native account and permission flows must be exercised separately. |
| [BFM: Canva trial breakdown](https://builtformars.com/ux-bites/canvas-trial-breakdown) | Explain what happens now and when access ends. | Vipi has no automatic charge for cardless access. Do not copy renewal or reminder promises. |
| [BFM: visible lifeboats](https://builtformars.com/ux-glossary/visible-lifeboats) | Keep history, restore and recovery actions visible when access or connectivity fails. | Do not imply that lost device-only history can be recovered without a backup. |

Mobbin references were inspected by the Apple agent using its available MCP tools. Its tool schema provides iOS and web search; this report does not claim Android-specific Mobbin coverage. Root’s BFM exact lookup and search metadata is retained in the private review evidence directory. The first BFM advisory call failed. A later call using actual Vipi observations succeeded; its advice and source URLs are retained in bfm-observed-advisory-r04.json. Suggestions remain hypotheses, not measured adoption results.

## Observed findings and fixes

| ID | Evidence | Finding | Owner and status |
| --- | --- | --- | --- |
| UX-01 | Android source, MainActivity.SettingsView | Terms, Privacy and Help labels remained hardcoded in a collection despite the translated resource catalog. | Fixed in the current source; corrected full-artifact screen recheck pending. |
| UX-02 | Apple source, Bot mini explanation | “Active Vipi subscription” incorrectly suggests a paid Base subscription is required during cardless access. | Apple changed it to active Vipi access; current localized screen recheck pending. |
| UX-03 | Android source audit by language agent | Report reasons, block/unblock confirmations, reading-speed labels, automatic language fallback and recovery fallback bypassed resource extraction. | Corrected source and locale resources; updated rendered states remain to be checked. |
| UX-04 | Android 96611a0, es-ES, normal text, light theme; es-welcome.png | Purpose, choose-languages action and labeled English/Spanish example fit without visible horizontal clipping. Preparing-voices text is visibly much fainter than surrounding copy. | Status colors corrected in source. Earlier ready/playing captures reviewed; current loading/error-state check pending. |
| UX-05 | Same welcome capture; earlier actual chat baseline | Instructions name Pause/Listen. Chat audio/pause actions were in the overflow menu; active Stop needed direct access. | Direct Stop now shown while preparing/playing. Native row interaction passes on both platforms; Android text width remains stable. Full signed-in conversation capture remains separate. |
| UX-06 | Apple nonliteral source audit | Nine language-download and speech-status/error strings were missing from localization extraction. | Apple imported nine Swahili additions with ordered placeholders; other locale drafts and actual layout need qualification. |
| UX-07 | Portuguese draft review | Malformed pt-PT inflections were found in provisional generated text. | Corrected drafts handed off; regional wording and actual screen review remain pending. |
| UX-08 | Actual iOS Spanish and Arabic diagnostic welcome screens | Multiline wrapper keys left the main headline and CTA in English; Arabic translated the brand, mirrored the mark, and used inappropriate letter spacing. | Corrected captures independently reviewed. Later full unsigned product build r08 compiles 7dd8280; screen evidence uses the isolated UI harness. |
| UX-09 | Arabic accessibility3 onboarding, settled scrolling | Content remained visible behind status-bar icons. | Native safe-area clipping fix 7dd8280 reviewed in both themes. Paragraph and CTA remain reachable at the captured scroll positions. |
| UX-10 | Contextual review of both native catalogs | 74 semantic errors included Resume rendered as summarize, deletion request as cancellation, Light as a physical light, and Delivered as a delivery fee. | Corrected in both candidates, followed by two German/Japanese verb refinements. Model review, not exhaustive native-speaker validation. |
| UX-11 | Both ChatSession.find implementations and displayed invitation username | Friend invitation displays @username but lookup rejects its leading @. | Both owners implemented exactly one optional leading ASCII @ for friend lookup, with strict remaining validation; signup rules unchanged. Apple nine native normalization cases pass. Network lookup on revised artifacts remains to be checked. |
| UX-12 | Apple subscription source and BFM account advisory | Generic payment-charged footer appears during cardless access alongside no-automatic-charge wording. | Fixed; English/French synthetic cardless plan captures show the end date, no-charge wording and restore/manage links without the paid footer. No live entitlement or purchase claim. |
| UX-13 | Android backup source | One generic failure path handles both input and output errors; a failed save can be described as an invalid password/damaged input. | Input/output errors separated in source; twelve-locale save-specific wording supplied. Recovery-path verification remains. |
| UX-14 | Native UIKit and Android accessibility APIs | Word-switch actions and some hints bypassed visible-text extraction and remained English. | Twelve-locale complete templates supplied; owners integrating and checking non-English native accessibility output. |
| UX-15 | Android profile creation and account activation routes | Both could open Plans immediately after account creation despite the accepted cardless onboarding. | Both routes changed to open Chats; entitlement refresh retained. Revised native route verification pending. |
| UX-16 | Android small outgoing-message metadata colors | #646C64 on #E0EDD4 calculates to 4.452:1. | Light secondary changed to #5D655D (4.945:1 on outgoing background); dark unchanged. Actual corrected message capture pending. |
| UX-17 | Actual French plan scrolling in Apple QA r06 | Bottom policy links are reachable, but a scrolled logo appears behind the top system region. | Owner applying the same native clipping correction and auditing related scroll surfaces before a batched rebuild. |

Earlier Android welcome capture artifact: QA package co.fallsoft.vipi.sourcecontextqa, source 96611a0, APK SHA-256 c784cbbe2d9ba13c53644d9718cba8696f99b351414b7e4f4e8ddda9f83d97f0, emulator 5622. Private capture: investigations/vipi-android-localization-20261117-r01/resource-validation/screens-96611a0/es-welcome.png. Later translations were not in that frozen build. Later interaction checks use the full-asset a816329 diagnostic app with separately pinned test revisions; its semantic-correction catalog is also superseded.

## Remaining interaction review

| Surface | What must be demonstrated | Current evidence |
| --- | --- | --- |
| Welcome and language selection | Explain learning through ordinary friend chat; usable example before signup; choose known/target language; preserve selection and scroll position sensibly. | Corrected Android Arabic/French and Apple Spanish/Arabic reviewed; Japanese wording and narrow headline refinement in progress. |
| Account, consent and hosted sign-in | Clear account action, reachable policy links, username requirements, cancellation and retry without losing onboarding choices. | Source review underway; revised full flow pending. |
| Empty chat list and invitation | Find or invite an existing friend; preview outgoing invite; cancel share safely; handle unknown username and inbound invite. | Mobbin comparison established; current runtime review pending. |
| Conversation and composer | Keyboard does not obscure draft; send/delivery/failure states remain distinct; retry does not duplicate messages; long and bidirectional messages stay readable. | Earlier native chat baseline exists; current candidate pending. |
| Inline immersion | Continuous no-tap switching, stable word slots, transliteration, readable mixed scripts, reveal/original controls, no disruptive switching during selection/scroll or screen-reader use. | Existing focused qualification is preserved; changed UI needs current recheck. |
| Speech | Prepared voices for both languages; readable loading/error states; original-script pronunciation; mixed message playback; prompt stop/cancel; safe navigation/background behavior. | Actual controller completion/cancel and embedded Stop checks passed; broad acoustic/pronunciation review remains separate. |
| Translation and downloads | Distinguish bundled words from full-message translation; accurate progress/cancel/retry; useful offline/low-storage/unsupported-pair states. | Missing-copy defects found; current runtime pending. |
| Free access and plans | 30-day account-bound access with no card or charge; correct expiry date; annual purchase shown only when verified; separate optional Bot mini; restore/manage accessible. | Backend tests and native clock checks passed; full revised UI and store offer change pending. |
| Bot conversation | Explain separate plan and message processing; show allowance and safe handling of unconfirmed requests; plain language errors. | Source and translation review underway. |
| Settings, history and recovery | Theme/word amount/language controls, backup availability and limitations, import/export/cancel, device recovery, blocked users and deletion progress. | Dynamic-copy gaps found; runtime pending. |
| Accessibility and locale variants | Both themes; large text; VoiceOver/TalkBack; Arabic RTL and mixed usernames; CJK and long German/Swahili; clear focus order and reachable controls. | Coverage must be tied to actual captures/interactions, not translated-key counts. |
| Public invite/help and store presentation | Invite landing works before installation; website and listings describe current behavior and trial terms; screenshots match the shipped app. | Local drafts exist; live terms still describe earlier offer until coordinated rollout. |

## Subsequent review observations

- Android Spanish onboarding ready and playing-state captures show Escuchar and Detener in the same action area. The native accessibility tree reports Pausar cambio de palabras for the icon. These observations establish labels and state feedback, not audible output or actual-chat stop reachability.
- Android French language selection used Continuer avec Espagnol. Interpolating a display language name creates article/case problems; the owner changed the next candidate to a simple localized Continue because the selected language is already visible.
- Android French account onboarding explains the free period without payment details, but the old sentence could imply another free period for an existing account. The next candidate explicitly limits this to new accounts and states there is no automatic charge. The lower content was subsequently reached by scrolling at normal text size; the language-selection Continue action was also reached at 2× French text. These checks used the older 96611a0 wording and need a brief updated-build recheck.
- Root inspected the live homepage and valid/invalid invitation pages using native browser control. The homepage describes ordinary friend chat, inline switching, local processing and the optional separate Bot plan. The valid invite shows a username and manual steps; the invalid invite says to request a fresh invitation. Both are currently English-only. The valid page intentionally says downloads are pending store approval. Store links and appropriate public-page localization remain release work; no real invitation was sent and no account was accessed.
- Actual iOS 4d34fbe Spanish and Arabic captures exposed missing exact multiline/custom-component keys: the headline and main CTA remained English. Arabic also translated the wordmark, mirrored the logo and spaced Arabic letters using Latin-style tracking. Root and the language reviewer independently inspected the original and corrected captures. These specific defects are fixed. The compact no-Keychain QA app omits language packs and account services, so it establishes UI behavior only.
- A synthetic Android conversation-row test passed for dwell, recomposition stability and seen-plus-new selection. It does not establish full conversation navigation, sound output or production account behavior.

Private public-page capture receipt: investigations/vipi-ux-review-20261117-r01/web-review-receipt.json. Root’s temporary browser tab was closed and desktop lease released; the existing store tab remains.

Root accepted one additional control change after source inspection and BFM/Mobbin comparison: when message audio is preparing or playing, Stop must be directly available without reopening overflow. Both owners implemented the direct control and checked native row interactions. Idle messages retain the minimal layout.

## Latest interaction evidence

- Android TalkBack run 987 passed on the actual bundled en-to-sw source route: “I like music.” displayed “I like muziki.” with music mapped to muziki, status PARTIAL / SOURCE_REFERENCE_PARTIAL, and zero model calls. With TalkBack enabled, automatic switching remained paused during the eight-second assertion; current menu, manual-word and long-list scroll assertions passed. Locale and accessibility services were restored. The earlier failed fixture used density 1.0 outside the production maximum 0.75; its diagnostic is retained rather than represented as a product failure.
- Android actual player callbacks establish completion, cancellation before rendering, and cancellation during playback. Recorded request-to-player-start was 276.5 ms and Stop returned in 2.6 ms for this single diagnostic run. These are not broad latency benchmarks, acoustic quality, or pronunciation acceptance.
- Apple QA r04 observed the real embedded row reach playing and the direct Stop action return its controller to ready with active=false. This used synthetic chat data and the compact QA app, not a live account conversation.
- Apple QA r05 independently reviewed Arabic accessibility3 screenshots in light and dark themes after the safe-area fix. The lower explanation and primary action are visible, and app content no longer overlaps status icons at those settled positions. French and Swahili settings captures include the localized maker label, but omit account and plan sections.
- Android fee12c9 full-asset QA captures show the literal Arabic vipi wordmark on one line and a reachable normal-size welcome action. French language selection shows Continuer; account copy explicitly limits the free thirty days to new accounts and says no payment method is required. These stills are scoped layout/copy checks, not completed account registration.
- Apple QA r06 renders production SubscriptionOfferView with a documented synthetic account-bound fixture and refresh disabled only in the harness. Root reviewed English and French no-charge/date wording. The owner then swiped the French page: policy links are reachable above the home indicator, while the top overlap remains a tracked defect.
- Xcode 26.6 is installed. Apple documents Accessibility Inspector as a way to emulate VoiceOver navigation in Simulator. Its evidence must be described separately from executing the iOS VoiceOver service; meaningful Inspector navigation is still pending. No physical-device requirement is inferred from that gap.

Private Android evidence: resource-validation/qa-talkback-final-987.log, qa-talkback-route-987.json, qa-playback-cancellation-a816329.json and qa-embedded-stop-1253.log. Native source/artifact receipts remain beside the captures. Apple evidence: apple-localized-ui-qa-r01/ar-accessibility-{light,dark}-scroll.png and the native localized-ui-qa-r04/chat-trace-901.jsonl.

A second BFM advisory addressed invitation, cardless access and recovery. Root accepted its clarity principles but rejected unsupported success claims: opening a share sheet must not be called “Invitation sent,” and the app must not say “No backup found” without actually checking a chosen location. No reminders, support service, or conversion result are promised. The detailed advisory and decisions are retained in bfm-account-advisory-r05.json.

Root also calculated 36 nominal source-color combinations, including the alpha background of inline word slots. The single below-reference combination was Android light small metadata; its correction is tracked above. These calculations use the [W3C contrast method and 4.5:1 ordinary-text reference](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html). They do not establish all rendered contrast, system colors, focus behavior, or accessibility compliance. Private evidence: native-color-review-r01.json.

No new languages are exposed by this review. The current product has 11 enabled languages. Language expansion remains a separately qualified capability change.

