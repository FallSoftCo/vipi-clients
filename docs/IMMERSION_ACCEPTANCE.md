# Immersion acceptance

User requirement, 2026-10-24: demonstrate the core UX across at least ten major languages and all pairs; prove transliteration for non-Roman languages. This is the immediate implementation priority.

Explicit user corrections: transliteration is mandatory for immersion, not optional. Non-Roman target languages need readable transliteration in the default in-place immersion display, with original script accessible. Missing or incorrect transliteration fails acceptance. Audio provides pronunciation; written pronunciation glyphs/IPA are not the user experience. Do not turn this into pronunciation notation or a lesson.

Speech cadence clarification: brief pauses between language spans may improve comprehension. Measure them and retain them for evaluation; silence duration alone is not a failure. Judge intelligibility, comfortable rhythm and predictable playback before making timing changes.

## Qualification set

English (en), Spanish (es), French (fr), German (de), Italian (it), Portuguese (pt), Arabic (ar), Mandarin Chinese (zh), Japanese (ja), Korean (ko). Ten languages yield 90 directed source→target pairs, independently exercised on Android and iOS. Self-pairs are not translation cases. Regional/script assumptions must be explicit; Mandarin initially uses Simplified Chinese, Portuguese variant must follow the model's declared capability.

## What a direction must demonstrate

1. A familiar conversation screen containing meaningful multi-message context, with immutable originals and local persistence. A labelled synthetic conversation is allowed for reproducible engineering QA, but must not be represented as real friend traffic.
2. Actual full-message local translation, then context-supported vocabulary replacements. Preserve source grammar in mixed mode. Low-confidence cases abstain. Do not count standalone dictionary substitutions as context proof.
3. Automatic in-place vocabulary flip-flop between familiar meaning and target form, with optional immediate reveal/hold, and full-sentence original/translation switching in the same bubble. Per-word tapping must not be required for comprehension. No second translation stack. Verify line wrapping, bubble geometry, scroll anchor, selection/copy, long messages and incoming/outgoing behavior. Automatic changes must not reflow the surrounding conversation or make the whole transcript flicker. Qualify dwell times in sustained reading, pause/pace controls, lifecycle cancellation, viewport eligibility and stable screen-reader behavior. Pause automatic changes during scrolling, composing, selection, explicit overrides and audio; listening uses a fixed visible-state snapshot. A no-tap reading task must demonstrate automatic access to both meaning and target vocabulary. Native preview timing and paragraph-layout checks now cover part of this requirement; real multi-message chats, incoming/outgoing interaction and sustained comprehension remain open.
4. Mandatory readable transliteration of non-Roman target text in the default in-place immersion display, with original script recoverable without a second stacked translation. Validate context-sensitive readings internally, including Chinese polyphonic characters, Japanese contextual readings/inflections and Arabic unvowelled ambiguity. Select and document a readable transliteration convention; no IPA/phonetic glyphs in the chat. Unknown readings must not be presented as certain. Native-script-only output or full translation is not a substitute for this requirement.
5. Local TTS uses the actual visible reading state and the intended language of each span. Romanized text is a display aid: pronunciation must use the underlying target-language text/readings, not an English voice reading Latin letters. Prepare both local voices for the chosen pair before playback. Render language spans into one continuous audio playback where latency permits; otherwise buffer the beginning and stream the remaining rendered segments through the same playback stream. Measure cold/warm first-audio latency and voice-transition gaps. Never assume the platform actually keeps both voice models resident. Explicitly test source word reveals, whole-message switching, replay, cancellation and stale-audio invalidation. Missing downloaded voices must have an honest, usable fallback.
6. Offline after preparation, with measured cold/warm latency, storage and memory. No network translator, model provider or transliteration fallback. Record the actual model/runtime versions and network state.
7. Accessibility: discoverable inline actions, screen-reader reading order/language, large type, reduced motion, RTL/mixed-direction punctuation, keyboard/composer and navigation restoration. Reuse the same interaction through onboarding and real chats.

## Evidence levels

- Availability: platform reports a pair supported. This is not execution evidence.
- Functional: the actual native pipeline runs locally and interactions preserve state.
- Linguistic: inspect expected meanings/readings against an authored reference corpus, recording wrong replacements, abstention/coverage and translation failures. A translation model's own output is not an independent gold reference.
- Usability: demonstrated tasks and observed failures in sustained conversation. Automated taps are not a human usability study.
- Acquisition: learning efficacy requires longitudinal user evidence and cannot be established by engineering tests. No efficacy claim follows from this acceptance gate alone.

Every matrix cell links the platform/build, exact source and target, originals, actual translations, selected spans, transliteration/readings, speech segmentation, network state, timing and interaction captures. Record failed/blocked/not-run separately. No placeholder passes, inferred symmetry, extrapolation from English→Spanish or silently excluded unsupported pairs.

## Corpus and review

Use a shared authored conversational corpus with independent expected senses/readings, then additional held-out cases. Include plans, food, family, work, travel, emotions, polysemy, idioms, negation, names, dates/numbers, URLs/code, emojis, repeated words, spelling variation, morphology and multi-sentence context. Review every selected replacement in the engineering set. Report precision and coverage separately; abstaining everywhere is not success. Thresholds must be stated before results are accepted and must not be relaxed to make a failing run pass.

The first prototype's dictionary/translation-presence heuristic has no broad quality evidence. Its failure analysis comes before selecting a richer local alignment model. Reusing model data or maintained native ML runtimes does not authorize a shared custom application/immersion engine.

## Platform limitation to resolve

Apple Translation cannot run in an iOS simulator. Actual Mac provider execution now covers 90 directions: 540 authored inputs and 2,880 fixed FLORES inputs. Network access remained available; these captures are neither offline verification nor physical iOS execution. iOS simulator alignment on those captured outputs is separately identified and source-hashed. The owner completed physical iPad UI authorization on 2026-10-25. Actual iPad execution now covers 90 directions and 540 authored inputs both online and with networking unavailable. Run 011 verifies every before/after network observation and restores Wi-Fi. The development app was first launched online for certificate trust; a cold offline release launch remains unqualified. Physical preview UI checks pass; contextual meaning, reading quality and real multi-message immersion still need separate proof.

## UX reference use

Automatic-flip review, 2026-10-24: inspection of both native renderers found manual link/tap handlers only, with no alternation scheduler. The earlier speech interaction checks do not prove automatic immersion. Mobbin's inspected Lyft language settings (https://mobbin.com/screens/39d9aef6-1473-4172-9517-f2d7d979f50b) show one automatic chat-translation switch and a preferred language; Skype's translation settings (https://mobbin.com/screens/c3cd3015-d9f6-437a-941f-30d6f05300f3) separate language and voice choice. Neither demonstrates inline timed alternation. BFM critique supported predictable controls, stable layout and freezing text during speech; its quiz and tap-as-mastery suggestions conflict with Vipi's product agreement and are not adopted. No reliable native word timestamps are currently qualified, so synchronized word highlighting is not an implemented promise.

Mobbin examples inspected on 2026-10-24:
- https://mobbin.com/screens/371ce83e-ec3b-4268-92f2-2fb17a3afcf2 — Bolt explains translation within the conversation while retaining the familiar composer.
- https://mobbin.com/screens/7e76c664-baed-4a74-8198-47bc5e690c2f — DoorDash states the other person's language and the automatic behavior in the empty conversation.

Use these for concise contextual explanation, not as proof that immersion works. Neither inspected screen demonstrates Vipi's in-place vocabulary interaction.

Built for Mars critique sources: https://builtformars.com/ux-bites/your-sound-is-off , https://builtformars.com/ux-bites/fake-fields-during-onboarding , https://builtformars.com/ux-bites/reactive-and-interactive-onboarding . Apply discoverable, reversible interaction and honest audio feedback. Avoid extra onboarding overlays or lesson-like activities. BFM explicitly does not establish linguistic or acquisition quality.

## Continuous preview implementation — 2026-10-24

Both native clients now repeat indefinitely while eligible, with 4.5-second target / 3-second meaning defaults and three persistent pace choices. Optional word taps reset the dwell; Pause holds the current face. Whole thoughts replace the same bubble. Non-Roman authored examples use readable Latin forms by default and expose the original script in Reading options. Full-sentence readings are authored too, not inferred from generic transliteration. Audio receives the underlying script and holds the visible language snapshot until playback ends.

The ten-language authored coffee-plan example exercises all 90 directions with native word boundaries (Android ICU, Apple NLTokenizer). Each direction selects at least two vocabulary spans in this fixture. Component checks exercise three widths and three text sizes on each platform. Android also captures script form. These are native layout/segmentation checks with authored source and target sentences: they do not pass the actual-translation, linguistic, conversation, or acquisition gates above. A single short example cannot establish morphology, polysemy or arbitrary-message coverage.

The first unmarked fixed-space prototype created unnatural gaps; a subsequent natural-paragraph version reserved only bubble height. The user then explicitly requested fixed space with a faint background and minimal rounding so the reservation feels intentional and tappable. The current candidate uses native inline blocks sized for all three forms. This changes the acceptance target: glyph positions and line breaks must remain fixed across automatic phases and script changes at a given width/font. Layout can change with screen width or text scaling. Test native copy separately because iOS attachments and Android replacement spans must return readable visible words, not internal placeholders or hidden source text.

Mobbin review also inspected Messages' translation actions (https://mobbin.com/screens/21672da4-1867-454d-9802-5075fa0597b1) and DoorDash's original-message action (https://mobbin.com/screens/0cf03c9e-f8ae-433a-92c3-ab0254400050). Vipi retains its single reading surface. BFM's Gmail case study (https://builtformars.com/case-studies/gmail) and button discoverability advice (https://builtformars.com/ux-bites/the-button-effect) informed concise controls, speech stability and natural paragraph spacing. Suggestions to stop after one cycle or add quizzes conflict with the user's explicit continuous immersion requirement and were not adopted.

A follow-up BFM critique identified pause-state clarity and temporary word overrides as risks to test. It supplied only loosely related sources, so it is advice rather than validation. Existing Pause/Resume and Listen/Stop controls already distinguish the states. A suggested “real conversation, not interactive” label would be inaccurate for this interactive authored preview and was rejected. Countdown animations and extra instructional overlays were not added without evidence of benefit.
