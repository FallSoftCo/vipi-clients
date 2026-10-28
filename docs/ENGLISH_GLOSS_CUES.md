# English dictionary gloss links and context cues — 2026-10-28

Incoming native-gloss IDs are direct links from foreign dictionary entries to
an English word. They are not additional explicit English sense labels.
For example, expensive has one explicit high-price relation plus nine incoming
gloss links from eight other languages. A Spanish caro occurrence can cover that
explicit price relation without carrying those foreign entry IDs.

Previously the context reader counted every incoming ID in its comparison of
source meanings with target meanings. That made an otherwise complete explicit
match appear narrower, forcing a rarer lexical cue even when the existing
corpus strongly supports a nearby grammatical cue. The preserved diagnostic
terms are in artifacts/english-gloss-cue-diagnostic-001.

For complete English-source nouns, adjectives and adverbs whose actual target
form has the same POS, the cue-selection comparison now uses all explicit
source relations when that set is nonempty. It does not drop source analyses,
invent missing senses, alter dictionary links, choose a translation or remove
incoming gloss links from actual matching. Empty explicit sets, other source
languages, verbs, attached carriers and cross-POS matches retain the previous
comparison. All existing context-support, case, ambiguity, compound, sentence,
number and reading requirements remain. The corpus threshold is still not an
accuracy estimate.

The initial adjective-only revision (native 520 / SMS 613) gains three authored
cost adjectives and two SMS spans on both platforms, with no losses.
The final noun/adjective/adverb revision (521 / 614) additionally gains four SMS
spans and suitcase→maleta in an intentional meaning-error control. The wrong
light→luminosa span remains withheld. That control is not counted as a genuine
conversation-coverage improvement.

Final targeted outputs match exactly across 185 cases, with 169 spans.
SMS ends at 88/200 messages and 120 spans on Android, 91/200 and 123 on iOS.
The three prior iOS-only spans remain. Both 602-case multilingual replays are
unchanged from the repeated-unit checkpoint: Android 264 messages / 411 spans,
iOS 265 / 411. Every new selected span is retained with contextual author
assessment in english-gloss-cue-review-001; the surrounding full translations
are not certified.

Source revisions are pinned in english-gloss-cue-candidate-001/002. Final
Android app SHA f55361280fb36592123ce1bd4b927a7750062ede09606f86f35388624d9163a3.
Reports: lexical-coverage-{android,simulator}-521/614.json,
bundled-conversations-android-020.json and simulator-021.json. Temporary public
QA witnesses are restored exactly; emulator restarts preserve its data.

The retained SMS has only about 5% of source words fully covered at maximum
availability. Native token denominators differ by platform and are recorded in
english-gloss-cue-review-001/depth.json. A message with one flip is not sufficient
immersion. The 90%-per-direction goal, broad depth, independent meaning review,
physical-device speech/accessibility and store delivery remain open. Accepted
lexical bundle 009 and phrase bundle 022 are unchanged; candidate dictionary
and witness data have not been published.
