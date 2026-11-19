# Full-message immersion

This is the current product contract from November 18, 2026. It supersedes the historical dictionary, fractional-word, density, exposure and automatic flip-timer designs. It describes required behavior; completion is established by native test and release receipts, not this document.

## Reading and listening

Every sent or received message is translated on the device into the language the user is learning. The conversation remains an ordinary chat with one reading surface per message. Non-Latin practice text uses live transliteration by default; Chinese pinyin retains tone marks. Audio always uses the complete underlying practice-language text.

| Interaction | Result |
|---|---|
| Tap a message | Play its complete practice-language audio. Tap that pending or playing message again to stop. |
| Hold the chat area | Reveal native-language meanings for all visible messages. Releasing or cancelling restores the practice display. Holding stays silent. |
| Double-tap the chat area | Toggle transliteration and practice script for the conversation. It does not also play audio. |
| Speaker toggle in the header | Enable or disable automatic playback of new messages. Initially off. |

The speaker toggle implements the user's request for ongoing playback. It is the stated default design choice, rather than an additional long-press action. Editable text, system navigation and screen-reader activation retain native behavior. Accessibility actions expose play/stop, reveal/restore, script switching and copying the authored original. A short contextual cue introduces the gestures to new and returning users without adding captions to every row.

The header menu also offers **Copy original message**. It opens a chooser of authored originals, including imported history; one tap copies the selected original. Opening the chooser stops pending and active audio, even when autoplay was already off. Cancel leaves the clipboard unchanged. The draft, selection, prior keyboard visibility and history position must survive dismissal. Copying does not make imported messages eligible for reporting.

Autoplay starts with messages that arrive after enabling it, including newly committed sent messages. It reads them in order without overlap. History loading, backup import and duplicate delivery acknowledgements do not enqueue playback. Turning it off, leaving the chat, backgrounding or changing the language pair cancels pending and active audio. A manual request wins over queued playback; the selected item is consumed once. A failed item is visibly retryable and does not stall every later message. An unavailable voice disables autoplay and provides an explicit recovery action.

## Native translation ownership

Each platform owns its implementation: Kotlin/coroutines on Android and Swift/concurrency on iOS. There is no shared application engine. Android uses ML Kit; iOS uses Apple Translation where available and the existing ML Kit adapter for supported directions unavailable through Apple, including Swahili. The adapter's actual device/model availability must be qualified.

Use these on-device provider APIs only. Do not add separately distributed translation or generative model weights, alternate inference runtimes, or cloud translation of friend chats. Platform-managed language and voice downloads remain necessary on devices that do not already have them.

1. Commit the authored message to the encrypted journal independently of translation. Display and speech never replace this authenticated original.
2. Feed durable sent and received message events to an account- and language-pair-owned translation service. The service outlives individual rows and navigation between chats. Restore/import catch-up uses bounded batches so new and visible messages remain responsive.
3. Identify the input language with a bounded advisory operation. Ambiguous or failed detection falls back to the configured native language. It cannot act as a dictionary-based eligibility gate.
4. Prepare required local models and translate the whole message. Already-practice-language input remains exact and receives a reverse translation for meaning. Third-language input gets actual input-to-practice and input-to-native translations.
5. Compute a live reading from the complete practice result. Keep transliteration data and its licenses, but no custom translation catalogs, authored sentence overrides or partial matching runtime.
6. Save only complete results in the existing account-encrypted vault. The cache key binds immutable message identity/text, language pair and translation policy. Corrupt or obsolete derived cache entries are recomputed; they never corrupt the source message.

Concurrent requests for the same message share one operation. Account or pair changes cancel the old owner and reject late completions. Preparing, failed and ready are distinct states. An unprepared model or failed translation must not be presented as a successful translation. Model downloads require connectivity; message translation has no server fallback.

Translation completion is not a guarantee of perfect semantics. Short ambiguous replies, names, code switching and unusual grammar need actual-output review. No fabricated confidence score, word blacklist or dictionary fallback should silently prevent an otherwise valid full-message request.

## Audio and layout

Prepare the practice-language voice once for the conversation. A chat-owned player serializes manual and automatic requests; recycling a message row does not stop audio. Long messages are chunked without truncating valid message content, and cancellation stops both pending synthesis and playback. The visible reading or temporarily revealed meaning is never used as the speech language.

Measure native paragraphs at the current width and text size, reserving sufficient space for meaning, practice script and transliteration. Hold and script switching should preserve the reader's position. Changes of width or accessibility text size may reflow normally. Verify light/dark contrast, RTL, keyboard behavior, long history and native screen-reader actions on the actual rendered screens.

## Qualification and delivery

The old store reviews have been withdrawn. The replacement must pass before resubmission:

- Real friend and vBot journeys: input focus, keyboard, send, receive, persistence, invitation and navigation.
- Actual local translation across the 11 configured languages and all 110 directed pairs; retain inputs, outputs, errors, source detection and timing. Separate model execution from semantic quality.
- Non-Latin transliteration, Chinese tone marks, underlying practice-text audio, completion and interruption.
- Whole-screen hold/release, double-tap suppression of audio, scrolling, large text, RTL and accessibility actions.
- Autoplay baseline, durable new arrivals, ordered queue, failures, manual interruption and lifecycle cancellation.
- Account/pair isolation, encrypted cache reuse, restored history, corrupted cache recovery and unchanged authenticated message text.
- Production-signed builds, package contents, privacy notices, corresponding source and truthful store metadata.

Controlled test providers establish application behavior, not native model accuracy or acoustic quality. Apple Translation does not run in the iOS simulator, and ML Kit's iOS simulator restrictions mean Swahili needs compatible actual-device proof. Native macOS provider results are useful evidence but do not certify the iOS app lifecycle.

Install the qualified production-signed Android upgrade over the existing package, preserving the user's account and chats. Inspect installed version and signature before installation, then verify the resulting installed version and launch. Submission and installation outcomes must be reconciled before retrying any uncertain external action.
