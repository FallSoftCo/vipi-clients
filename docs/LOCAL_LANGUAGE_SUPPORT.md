# Local language support — manual review record

Updated 2026-11-19. Owner: Vipi team. Release remains on hold.

This is the durable record to consult before expanding the language picker or making a support claim. A translation SDK language, an installed voice, a romanized string, and a usable Vipi language are different facts. The 59 ML Kit languages are candidates. They are not 59 accepted Vipi languages.

The owner requires translation and local speech support to match one to one, with transliteration for non-Latin text. Verify those features directly in the app and record the result here. Unit and integration tests protect routing, cancellation, caching, and state transitions; they do not certify speech or transliteration quality. The prepared native capability-inventory test was never run and has been removed.

## What the platform documentation establishes

- [ML Kit translation languages](https://developers.google.com/ml-kit/language/translation/translation-language-support) lists the 59 candidates below. [Translation guidance](https://developers.google.com/ml-kit/language/translation) describes an on-device translator intended for simple/casual text; translation availability is not a quality guarantee.
- [Apple speechVoices](https://developer.apple.com/documentation/avfaudio/avspeechsynthesisvoice/speechvoices()) describes voices available on the current device. [Apple voice setup](https://support.apple.com/en-us/111798) explains downloading voices. An absent installed voice must be distinguished from a language the platform cannot provide.
- [Android TextToSpeech](https://developer.android.com/reference/android/speech/tts/TextToSpeech) distinguishes missing voice data from an unsupported language. [Voice.isNetworkConnectionRequired](https://developer.android.com/reference/android/speech/tts/Voice#isNetworkConnectionRequired()) identifies voices that require a network. Vipi needs a working local voice.
- [Apple toLatin](https://developer.apple.com/documentation/corefoundation/kcfstringtransformtolatin) converts what it can to Latin script and treats ideographs as Mandarin. It is unsuitable as a generic Japanese reading engine. [ICU's transform documentation](https://unicode-org.github.io/icu/userguide/transforms/general/) describes script conversion, which must not be presented as reliable pronunciation for arbitrary languages.
- The current [Apple feature list](https://www.apple.com/ios/feature-availability/) describes iOS/iPadOS27. Our retained Simulator is iOS26.5. Do not use the newer list to certify this older runtime.

## Findings already inspected

The existing native macOS26.6 inventory reported 22 base translation languages and voices for 38 of the 59 candidates. Vipi also has an existing bundled Swahili voice. These are inventory facts, not 39 qualified iOS languages. No audio was played during that inventory.

Arabic, Hebrew and Persian generic conversions leave vowels unresolved. For example, Hebrew `שלום! מה שלומך?` became `şlwm! mh şlwmk?`. Urdu `سلام! آپ کیسے ہیں؟` became `slạm! ập ḵy̰sai ḥy̰◌̃?`; the dotted circle is an explicit unresolved output. Thai output has stacked marks that need a direct readability review. These findings must remain open even if a test says the output contains Latin characters.

Chinese uses the existing tone-marked pinyin adapter; Japanese and Korean use their language-specific adapters. Those implementations still need direct app review with ordinary messages, names, punctuation and mixed-script text. Audio must use the actual practice-language text, never the Latin reading.

Both hosts remain muted at the owner's request. No acoustic-quality or listening approval is claimed. A visible playback state, nonempty audio file, or successful callback cannot establish pronunciation quality.

## Direct app observations on 2026-11-19

These checks used the retained iOS26.5 Vipi QA app and its manually operated reading view. The view supplies the target sentence; the actual production reading engine generates the displayed reading. No XCTest runner or prefilled reading result was used. This establishes behavior of the inspected samples, not translation accuracy or whole-language coverage.

| Language | Supplied target | Reading visibly inspected | Result and limitation |
| --- | --- | --- | --- |
| Chinese | 银行行长正在走路。 | yínháng hángzhǎng zhèng zài zǒu lù。 | Tone marks present; the two meanings of 行 have different readings in this sample. |
| Chinese | 我需要水。 | wǒ xū yào shuǐ。 | Changed the sample with native accessibility input; the reading updated live and retained tone marks. |
| Japanese | ZoëとJoséにメッセージを送った。 | Zoë to José ni messēji wo okutta。 | Names and their accents preserved; the surrounding Japanese was transliterated live. |
| Korean | 같이 학교에 갑니다. | gat-i haggyoe gabnida. | Orthographic conversion is visible. This is not a phonetic transcript: spelling and spoken sound changes differ. Use native-script TTS for pronunciation. |

Evidence: native `manual-chinese-reading-r01.png`, `manual-chinese-authored-r01.png`, `manual-japanese-reading-r01.png`, and `manual-korean-reading-r01.png` under `/Users/Apple/Development/vipi-translation-reset-20261118-r01/`. The original native broker job IDs are retained in the investigation's manual review receipt.

Physical pointer taps and double taps did not produce a visible change in this manual window; native accessibility selection did. A short process sample showed an idle main run loop, not evidence of a blocked main thread. The cause is unresolved, so these observations do not accept the gesture path or TTS playback. No pronunciation listening claim is made.

## Per-language evidence

All rows below are documented ML Kit translation candidates. “Listed” means enumerated on **macOS26.6**, not manually accepted on mobile. “Absent” means not enumerated there, not permanently unsupported. Every new mobile language remains pending direct app review. The companion [JSON record](local-language-support.json) retains exact inspected readings and separate iOS/Android review fields.

| Language | Code | Mac translation | Mac local voice | Reading route / known issue |
| --- | --- | --- | --- | --- |
| Afrikaans | af | Absent | Absent | Latin script; normally no reading needed |
| Albanian | sq | Absent | Absent | Latin script; normally no reading needed |
| Arabic | ar | Listed | Listed | Foundation toLatin; unwritten vowels unresolved |
| Belarusian | be | Absent | Absent | Foundation toLatin |
| Bengali | bn | Absent | Listed | Foundation toLatin |
| Bulgarian | bg | Absent | Listed | Foundation toLatin |
| Catalan | ca | Absent | Listed | Latin script; normally no reading needed |
| Chinese | zh | Listed | Listed | pinyin-pro 3.29.5, tone marks retained |
| Croatian | hr | Absent | Listed | Latin script; normally no reading needed |
| Czech | cs | Absent | Listed | Latin script; normally no reading needed |
| Danish | da | Listed | Listed | Latin script; normally no reading needed |
| Dutch | nl | Listed | Listed | Latin script; normally no reading needed |
| English | en | Listed | Listed | Latin script; normally no reading needed |
| Esperanto | eo | Absent | Absent | Latin script; normally no reading needed |
| Estonian | et | Absent | Absent | Latin script; normally no reading needed |
| Finnish | fi | Absent | Listed | Latin script; normally no reading needed |
| French | fr | Listed | Listed | Latin script; normally no reading needed |
| Galician | gl | Absent | Absent | Latin script; normally no reading needed |
| Georgian | ka | Absent | Absent | Foundation toLatin |
| German | de | Listed | Listed | Latin script; normally no reading needed |
| Greek | el | Absent | Listed | Foundation toLatin |
| Gujarati | gu | Absent | Absent | Foundation toLatin |
| Haitian Creole | ht | Absent | Absent | Latin script; normally no reading needed |
| Hebrew | he | Absent | Listed | Foundation toLatin; unwritten vowels unresolved |
| Hindi | hi | Listed | Listed | Foundation toLatin |
| Hungarian | hu | Absent | Listed | Latin script; normally no reading needed |
| Icelandic | is | Absent | Absent | Latin script; normally no reading needed |
| Indonesian | id | Listed | Listed | Latin script; normally no reading needed |
| Irish | ga | Absent | Absent | Latin script; normally no reading needed |
| Italian | it | Listed | Listed | Latin script; normally no reading needed |
| Japanese | ja | Listed | Listed | CF Japanese tokenizer and existing reading adapter |
| Kannada | kn | Absent | Listed | Foundation toLatin |
| Korean | ko | Listed | Listed | CF Hangul and existing reading adapter |
| Latvian | lv | Absent | Absent | Latin script; normally no reading needed |
| Lithuanian | lt | Absent | Absent | Latin script; normally no reading needed |
| Macedonian | mk | Absent | Absent | Foundation toLatin |
| Malay | ms | Absent | Listed | Latin script; normally no reading needed |
| Maltese | mt | Absent | Absent | Latin script; normally no reading needed |
| Marathi | mr | Absent | Absent | Foundation toLatin |
| Norwegian | no | Listed | Listed | Latin script; normally no reading needed |
| Persian | fa | Absent | Absent | Foundation toLatin; unwritten vowels unresolved |
| Polish | pl | Listed | Listed | Latin script; normally no reading needed |
| Portuguese | pt | Listed | Listed | Latin script; normally no reading needed |
| Romanian | ro | Absent | Listed | Latin script; normally no reading needed |
| Russian | ru | Listed | Listed | Foundation toLatin |
| Slovak | sk | Absent | Listed | Latin script; normally no reading needed |
| Slovenian | sl | Absent | Listed | Latin script; normally no reading needed |
| Spanish | es | Listed | Listed | Latin script; normally no reading needed |
| Swahili | sw | Absent | Existing bundled Swahili voice | Latin script; normally no reading needed |
| Swedish | sv | Listed | Listed | Latin script; normally no reading needed |
| Tagalog | tl | Absent | Absent | Latin script; normally no reading needed |
| Tamil | ta | Absent | Listed | Foundation toLatin |
| Telugu | te | Absent | Listed | Foundation toLatin |
| Thai | th | Listed | Listed | Foundation toLatin; stacked marks; readability pending |
| Turkish | tr | Listed | Listed | Latin script; normally no reading needed |
| Ukrainian | uk | Listed | Listed | Foundation toLatin |
| Urdu | ur | Absent | Absent | Foundation toLatin; unresolved placeholder |
| Vietnamese | vi | Listed | Listed | Latin script; normally no reading needed |
| Welsh | cy | Absent | Absent | Latin script; normally no reading needed |

## Direct review procedure

For each platform and candidate, select the language in the actual app. Record the OS, app revision, voice engine/name and whether voice data is already installed, can be downloaded, or is unsupported. Enter an ordinary message and inspect the actual local translation and default reading. Include a name, a number, punctuation and a link; these expose errors that a greeting alone misses.

Tap the message once and inspect playback beginning, stopping, retry, and subsequent playback with the app offline. Confirm that the practice-language text is spoken even while the reading is displayed. Double-tap to change script and hold the background to reveal the original; verify that these gestures retain the same audio meaning. Record what was actually seen and any captured audio without calling it a listening review. Listening/phonetic quality remains pending until evaluated from audio.

Do not list a language as fully supported until translation, local TTS and any required reading have direct evidence on the applicable platform. Device setup requirements must be visible before onboarding completes. Existing users' language choices and message history must be preserved if readiness changes.

## Evidence locations

- `investigations/vipi-translation-reset-20261118-r01/world-class-quality-20261119-r01/native-language-inventory-r01.json`: retained macOS API inventory, not a test or mobile acceptance.
- `ios-build-r28/native-receipt.json` under the same investigation: candidate build compiled; no language quality claim.
- `ios-units-r10/SUPERSEDED-NOT-EXECUTED.json`: prepared capability-test packet explicitly retired before dispatch.
- Add each direct app observation here with its screenshot/audio path, app revision, platform and concrete outcome. Never silently overwrite a failure with a later pass count.
