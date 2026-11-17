# Vipi UI and UX review — 2026-11-17

Status: in progress. Reference research and source review are complete enough to guide fixes; current native screen and interaction qualification is still running. This report does not certify “world class,” language accuracy, or store readiness.

## Evidence rules

Record the source revision, installed artifact hash, platform/device, locale, theme and text size for each capture. A still establishes only the visible layout and wording. Playback, continuous switching, keyboard handling, recovery and subscription expiry require observed interactions or focused native checks. Earlier screenshots remain useful baselines, not evidence for a changed build.

Native owners keep source changes isolated until their actual candidates are qualified. No repeated signing, upload, purchase, test notification or external message is required by this review.

## Reference comparisons

| Reference inspected through MCP | Application to Vipi | Limit |
| --- | --- | --- |
| [Mobbin: WhatsApp invite](https://mobbin.com/flows/cce40094-5111-4ee4-a7f5-90737cda749a?tab=screens) | Clear share-invite action, with the user choosing the recipient in the native share sheet. | iOS reference; not Android-specific evidence. |
| [Mobbin: Signal first chat](https://mobbin.com/flows/a9c2cf2f-20b9-428d-8f31-c0cafe09a77d?tab=screens) | Empty state explains the next action and exposes compose. | Vipi must also explain why ordinary friend conversations teach words. |
| [Mobbin: Speak audio](https://mobbin.com/flows/1a1c0daf-879b-42f3-8100-9e03af3705f7?tab=screens) | Playback has distinct preparing, playing and stop states in a stable location. | Does not prove Vipi voice readiness or pronunciation. |
| [Mobbin: Glovo translation](https://mobbin.com/flows/50aecc0a-c9ce-49bd-b4ae-41f9a1f3857a?tab=screens) | Keep chat geometry familiar and make translation state understandable. | Vipi’s automatic inline switching needs its own interaction validation. |
| [Mobbin: Tide Guide subscription](https://mobbin.com/flows/5bef40b5-8760-4eb3-b232-dfaf5da7b41b?tab=screens) | Separate current access, renewal date and subscription management. | Its offer is not Vipi’s cardless access period. |
| [BFM: context and feature onboarding](https://builtformars.com/ux-bites/context-feature-onboarding) | Teach a control when it becomes useful, beside the actual example or chat. | A pattern recommendation, not measured Vipi adoption evidence. |
| [BFM: Signal account creation](https://builtformars.com/case-studies/creating-a-signal-account) | Ask for permissions in context; explain validation errors and the next recovery action. | Native account and permission flows must be exercised separately. |
| [BFM: Canva trial breakdown](https://builtformars.com/ux-bites/canvas-trial-breakdown) | Explain what happens now and when access ends. | Vipi has no automatic charge for cardless access. Do not copy renewal or reminder promises. |
| [BFM: visible lifeboats](https://builtformars.com/ux-glossary/visible-lifeboats) | Keep history, restore and recovery actions visible when access or connectivity fails. | Do not imply that lost device-only history can be recovered without a backup. |

Mobbin references were inspected by the Apple agent using its available MCP tools. Its tool schema provides iOS and web search; this report does not claim Android-specific Mobbin coverage. Root’s BFM exact lookup and search metadata is retained in the private review evidence directory. One BFM advisory call failed; no advice was fabricated from that failure.

## Observed findings and fixes

| ID | Evidence | Finding | Owner and status |
| --- | --- | --- | --- |
| UX-01 | Android source, MainActivity.SettingsView | Terms, Privacy and Help labels remain hardcoded in a collection despite the translated resource catalog. | Android notified; source fix and native recheck pending. |
| UX-02 | Apple source, Bot mini explanation | “Active Vipi subscription” incorrectly suggests a paid Base subscription is required during cardless access. | Apple changed it to active Vipi access; current localized screen recheck pending. |
| UX-03 | Android source audit by language agent | Report reasons, block/unblock confirmations, reading-speed labels, automatic language fallback and recovery fallback bypass resource extraction. | Android notified; source fixes and recheck pending. |
| UX-04 | Android 96611a0, es-ES, normal text, light theme; es-welcome.png | Purpose, choose-languages action and labeled English/Spanish example fit without visible horizontal clipping. Preparing-voices text is visibly much fainter than surrounding copy. | Root and language agent independently inspected. Increase status readability; capture ready and failure states. |
| UX-05 | Same current welcome capture; earlier actual chat baseline | Instructions name Pause/Listen. Onboarding pause is icon-only; chat audio/pause actions are in the overflow menu. Discoverability and quick Stop need interaction review. | Android capturing current menu/playback states; no usability success claimed from stills. |
| UX-06 | Apple nonliteral source audit | Nine language-download and speech-status/error strings were missing from localization extraction. | Apple imported nine Swahili additions with ordered placeholders; other locale drafts and actual layout need qualification. |
| UX-07 | Portuguese draft review | Malformed pt-PT inflections were found in provisional generated text. | Corrected drafts handed off; regional wording and actual screen review remain pending. |

Current Android capture artifact: QA package co.fallsoft.vipi.sourcecontextqa, source 96611a0, APK SHA-256 c784cbbe2d9ba13c53644d9718cba8696f99b351414b7e4f4e8ddda9f83d97f0, emulator 5622. Private capture: investigations/vipi-android-localization-20261117-r01/resource-validation/screens-96611a0/es-welcome.png. Later translations were not in that frozen build.

## Remaining interaction review

| Surface | What must be demonstrated | Current evidence |
| --- | --- | --- |
| Welcome and language selection | Explain learning through ordinary friend chat; usable example before signup; choose known/target language; preserve selection and scroll position sensibly. | Current Android Spanish welcome still reviewed. Updated Apple and remaining flow pending. |
| Account, consent and hosted sign-in | Clear account action, reachable policy links, username requirements, cancellation and retry without losing onboarding choices. | Source review underway; revised full flow pending. |
| Empty chat list and invitation | Find or invite an existing friend; preview outgoing invite; cancel share safely; handle unknown username and inbound invite. | Mobbin comparison established; current runtime review pending. |
| Conversation and composer | Keyboard does not obscure draft; send/delivery/failure states remain distinct; retry does not duplicate messages; long and bidirectional messages stay readable. | Earlier native chat baseline exists; current candidate pending. |
| Inline immersion | Continuous no-tap switching, stable word slots, transliteration, readable mixed scripts, reveal/original controls, no disruptive switching during selection/scroll or screen-reader use. | Existing focused qualification is preserved; changed UI needs current recheck. |
| Speech | Prepared voices for both languages; readable loading/error states; original-script pronunciation; mixed message playback; prompt stop/cancel; safe navigation/background behavior. | Current preparing-state still only; native ready/error/playback checks pending. |
| Translation and downloads | Distinguish bundled words from full-message translation; accurate progress/cancel/retry; useful offline/low-storage/unsupported-pair states. | Missing-copy defects found; current runtime pending. |
| Free access and plans | 30-day account-bound access with no card or charge; correct expiry date; annual purchase shown only when verified; separate optional Bot mini; restore/manage accessible. | Backend tests and native clock checks passed; full revised UI and store offer change pending. |
| Bot conversation | Explain separate plan and message processing; show allowance and safe handling of unconfirmed requests; plain language errors. | Source and translation review underway. |
| Settings, history and recovery | Theme/word amount/language controls, backup availability and limitations, import/export/cancel, device recovery, blocked users and deletion progress. | Dynamic-copy gaps found; runtime pending. |
| Accessibility and locale variants | Both themes; large text; VoiceOver/TalkBack; Arabic RTL and mixed usernames; CJK and long German/Swahili; clear focus order and reachable controls. | Coverage must be tied to actual captures/interactions, not translated-key counts. |
| Public invite/help and store presentation | Invite landing works before installation; website and listings describe current behavior and trial terms; screenshots match the shipped app. | Local drafts exist; live terms still describe earlier offer until coordinated rollout. |

## Subsequent review observations

- Android Spanish onboarding ready and playing-state captures show Escuchar and Detener in the same action area. The native accessibility tree reports Pausar cambio de palabras for the icon. These observations establish labels and state feedback, not audible output or actual-chat stop reachability.
- Android French language selection used Continuer avec Espagnol. Interpolating a display language name creates article/case problems; the owner changed the next candidate to a simple localized Continue because the selected language is already visible.
- Android French account onboarding explains the free period without payment details, but the old sentence could imply another free period for an existing account. The next candidate explicitly limits this to new accounts and states there is no automatic charge. The lower content’s scroll reachability still needs interaction verification.
- Root inspected the live homepage and valid/invalid invitation pages using native browser control. The homepage describes ordinary friend chat, inline switching, local processing and the optional separate Bot plan. The valid invite shows a username and manual steps; the invalid invite says to request a fresh invitation. Both are currently English-only. The valid page intentionally says downloads are pending store approval. Store links and appropriate public-page localization remain release work; no real invitation was sent and no account was accessed.
- A synthetic Android conversation-row test passed for dwell, recomposition stability and seen-plus-new selection. It does not establish full conversation navigation, sound output or production account behavior.

Private public-page capture receipt: investigations/vipi-ux-review-20261117-r01/web-review-receipt.json. Root’s temporary browser tab was closed and desktop lease released; the existing store tab remains.

No new languages are exposed by this review. The current product has 11 enabled languages. Language expansion remains a separately qualified capability change.

