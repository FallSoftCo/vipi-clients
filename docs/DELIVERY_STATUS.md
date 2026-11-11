# Current delivery status

Updated 2026-11-10. Vipi is **not ready for store submission or public customer access**. Restricted staging is live. The remaining work is conversational language quality and progression, complete native integration, release qualification, company provider authentication and real store/push/bot configuration. Historical `VERIFICATION.md` entries retain earlier observations and failures; they do not supersede this status.

Automatic source-only vocabulary is now enabled for all 110 directions among
the eleven supported languages. The new pinned catalog adds 108 directions;
the existing English→Japanese and English→Swahili providers keep priority.
Both actual default engines reproduce the accepted finite fixture outputs and
reject the tested unsafe cases. This closes the routing gap, not the vocabulary
coverage gap. The larger legacy alignment databases still do not authorize
automatic substitutions without their required evidence.

A separate reviewer froze 132 natural-style synthetic friend messages before
seeing the active catalog. Both native default engines emitted words in only
39 of 1,320 directed cases (2.95%); eight source languages emitted none. Much of
the English output was pronouns. Originals were preserved and no automatic
translation or model-readiness calls occurred. Review found no clear wrong-sense
substitution in those emitted spans, but this sparse exposure is insufficient
for the intended everyday experience. New everyday and high-frequency content
increments are being independently reviewed; they are not yet shipped. This
synthetic sample is a usefulness warning, not a population accuracy estimate.

Both native clients now use the pinned local CLD2 detector. Actual Android and
Apple tests reproduce the same 87 detector cases and preserve originals in the
tested known-error routes. English vocabulary switching remains functional.
The detector can still be wrong or abstain, including on short Swahili messages;
its reliability flag is not a translation-quality score. The two source fixes
preserve the measured outputs and pass the bounded native parser exercise.
These changes do not remove the optional Google translation SDK or qualify a
new store release binary. The Mac signing hold and provider-authentication
dependencies remain unchanged.

The accepted default engine took about 6 ms median in the instrumented Apple
fixture run and 11 ms on Android. Those warmed measurements exclude complete
chat presentation. Android's isolated cold row presentation took 1.32–2.34 s;
do not describe all visible responses as single-digit milliseconds. Native
continuous-flip/readings checks passed on additional language pairs. Apple
checks used isolated components because unsigned normal startup encounters a
keychain read error. No receipt was cleared and no signing retry was made.

## Source and host authority

The owner has reserved the iPad for 8bar Club. Continue Vipi validation in the existing simulators and on the native Mac; do not wait for or resume iPad work. Hardware-specific evidence limits remain identified separately from this work plan.

The canonical workspace is `/home/ai/Development/vipi-production-20261107`, branch `delivery/production-20261107`. Private checkpoints preserve committed source on the consolidated host; the exact verified references are in `BUILD_ENVIRONMENTS.md` and private delivery receipts. Source is private until the client corresponding-source release has been assembled and checked.

OZZZ-OS and OZZZ-GPU are provider-cancelled. The relay uses `fallsoft-production-20261106`; retained bulk data uses Storage Box `u684605`. The November 8 owner directive moves new Apple work to native `apple@macbook-pro`. The separate migration owner completed verified preservation and retired the VM's exact backing disk on November 9; do not recreate it. Preserve native projects, accounts and unrelated applications. Historical VM results below remain historical evidence. Android uses the existing QA emulator on system76.

## Demonstrated behavior and remaining work

The owner's latest November 10 direction narrows the first release to entirely
local single-word and short-phrase immersion. Prior full-sentence translation,
quality-estimation and cloud-model investigations remain research evidence, not
prerequisites for this initial experience. The content priority is meaningful
everyday vocabulary and reusable small phrases in the user's own conversations,
with source-language grammar, continuous stable inline flips, readings and local
audio. Matching must still respect contextual senses, complete units and protected
text. Automatic misses now retain original text without invoking a translation
model or readiness/download check. Explicit on-device full translation remains a
separate action. Familiarity records extend target display time after exposure
on different days; they do not claim mastery or expand the vocabulary budget.
Android encrypted persistence is qualified; the unsigned Apple test remains
blocked by keychain entitlement error -34018. Broad useful coverage is unfinished.
A phrase proposal count or a pronoun-only match does not establish it.

The November 10 native increment adds eight Japanese and fifteen Swahili short
phrases, preserving original-script audio and Japanese readings. Content phrases
now precede their smaller overlapping entries; finite reviewed source contexts
keep priority. Two independent agent reviews found no significant error in the
59 changed native outputs from the retained 70 authored sources. These exposed
controls are not broad conversation accuracy or native-human certification.
An Android cache-identity regression was caught by inspecting actual output,
corrected, and covered by stronger outcome assertions; the rejected run remains
in the evidence. Final packaged-asset and default-route receipts are retained in
`qa/immersion/local-release-r01`.

The original Vipi icon, semantic light/dark controls, interactive pre-account
example and accessible account form are now implemented. The UX agent used
Mobbin screens and Built for Mars onboarding guidance; exact sources, original
icon provenance and actual visual-review scope are retained in
`qa/design/vipi-identity-r01`. This work does not certify the complete customer
journey, purchases, background delivery, or store release.

The following plain-language pass now leads with **Chat with friends. Learn new
words.** Both clients explain the automatic word/phrase switching and separate
optional full-message translation. Reading controls use Latin letters and
Slower/Standard/Faster; stored settings and behavior are unchanged. Both native
builds passed. Android's actual onboarding and four prepared non-Latin previews
passed; iOS component checks passed themes, largest text, step scroll reset and
six stable automatic flips. These are copy/layout checks, not new conversational
coverage or signed account-flow evidence. See `qa/design/plain-language-r01`.

Store reconciliation on November 10 found the company Google Play account
accessible and the package name available, but no Vipi app was created. The
form's export certification is unsubmitted. The updated technical assessment
in `release/EXPORT_ASSESSMENT.md` removes obsolete blanket source-notification
and annual-report assumptions; final release facts and dependency terms remain
separate. App Store Connect remains signed
out and both Mac signing keychains remained locked at the read-only check;
no signing attempt followed. Existing Apple sandbox server-notification success
is preserved and was not replayed. Google Cloud requires company password
verification; Firebase reports HTTP v1 messaging disabled. The live backend
remains restricted staging with subscriptions unenforced and no APNs, FCM or
DeepSeek configuration enabled. Public-page copy and the local exposure-record
privacy addendum are now live at `4473238`. The scoped deployment preserved the
database/schema, environment configuration and shared nginx/PostgreSQL services;
public routes return 200, protected routes still reject unauthenticated requests.
The subsequent Vipi-only identity configuration now uses the production WorkOS
application, restricted to two owned review accounts. Its activation and account
readback are verified; public registration remains off. The current Vipi icon
and light/dark hosted sign-in screens are also verified. Android production PKCE,
native profile creation and encryption-key enrollment now pass for one owned
review account against this restricted service. The original observer timeout
was reconciled with actual session/token state and read-only backend results:
one active device, one public bundle and twenty prekeys. No purchase, push or
peer-exchange qualification follows from this account flow. See
`qa/backend/native-production-auth-android-r01`,
`qa/backend/production-auth-staging-r01` and `qa/design/hosted-signin-r01`.
The actual signed Android production bundle also passed local package/version,
production-configuration, signature and ARM64 split/alignment checks. Its measured
ARM64 download estimate is 408,542,274 bytes. It has not been installed against
the production service, uploaded or accepted by Google Play.
The matching iOS device Release archive passed with 637 committed inputs and
13 bundled privacy manifests. It is intentionally unsigned, has no embedded
profile and must not be uploaded. The signing hold was preserved. Exact binary
hashes and receipt bindings are in `release/build-artifacts-20261110.json`.
Those earlier artifacts predate the language-detector and phrase-pack changes
and are explicitly superseded for submission.

Both clients now expose an ordinary **Sign in again** action when authentication
expires, bound to the existing account. Device-replacement recovery remains a
separate action; the change does not sign out, delete history or silently switch
accounts. Focused native recovery checks pass. Apple's unsigned tests use a
synthetic session and do not qualify actual keychain persistence or live OAuth.

Before that narrowing, all immersion techniques were evaluated as candidates,
including immediate local word/phrase flips followed by whole-sentence local or
language-model translation. An unsigned native Mac diagnostic completed 162
forward/backward sentence pairs across nine target languages and 12 authored
Spanish quality controls in 19.78 seconds. These are only 18 distinct English
sources, including eight previously exposed conversation messages. Both
independent agent reviews flag the same six material native-output errors;
they differ on five minor-versus-compatible judgments. An exploratory English
sentence-embedding threshold rejects all six errors but retains only 81/162
native outputs. It is not calibrated, native-human gold, or a production gate.
Apple and ML Kit translation APIs expose no semantic-quality confidence score.
Hindi was uninstalled and Swahili unsupported on this Apple path; neither is
credited as covered. No model download, signing retry or app activation occurred.
See `qa/immersion/hybrid-confidence-r01/root-conclusion-r01.json` and the retained
blinded reviews, timing evidence and reproducible probe.

The team's cost calculator covers 576 explicitly assumed scenarios using current
official DeepSeek Flash prices. At peak, with 200 input/60 output tokens per
forward call, 50/200/500 cloud translations per day cost $2.41/$9.64/$24.09 per
paid year before trials and other costs. A $12 annual local-first plan with a
bounded optional cloud allowance remains plausible; unlimited heavy cloud
translation is not supported by that calculation. Cloud routing frequency,
provider quality/latency, actual tokens and overhead remain unmeasured. Existing
Base/Bot mini prices, independent trials and entitlements are unchanged. The
existing GPU host has been retired; self-hosting cannot assume free GPU capacity.
The pure calculator and its assumptions are retained beside the diagnostic.

A separately pinned, offline small translation-model pilot now completes six
exposed sources across Spanish, Japanese and Swahili. NiuTrans LMT-60-0.6B with
five-beam cached CPU decoding took 203 seconds for 18 cases and peaked at 4.90 GB
process memory. Both reviewers identify the same material Swahili meaning
change; their minor-versus-compatible labels differ. The first three judgments
were previously disclosed to the peer reviewer; the remaining 15 were reviewed
independently. This is neither phone qualification nor broad accuracy evidence.
The original 54-case uncached run and its smaller continuation were explicitly
stopped and retained. Cached decoding matched the three completed baseline
outputs exactly; no general parity claim follows. See the retained small-model
conclusion and approach register. Cloud comparisons include official OpenAI and
DeepSeek pricing, but no paid provider inference or customer text was submitted.

Bulk development-data mining also completed: 14,010 dictionary phrase lexemes
and 59,945 complete parallel-sentence proposals retain alternatives and provenance.
These are a review pool, not new activated coverage. On the exposed 9,535-message
TRAIN set, mechanically compatible phrase entries cover only 839 Japanese,
129 Swahili and 927 Spanish native words before semantic/selection checks; exact
whole-sentence corpus matches remain rare. Raw dictionary, grammatical and
round-trip signals are not interchangeable with contextual correctness.

| Area | Latest demonstrated result | Remaining gate |
|---|---|---|
| Service | Restricted staging runs `4473238`, same database/schema and credentials. Plain-language homepage/help and the exposure-record privacy disclosure are live; Apple Sandbox verification remains configured. Public routes return 200 with CSP and protected routes remain closed. | Production registration/configuration and real provider credentials. |
| Human chat | Actual native E2EE exchange, out-of-order replies, replay rejection, foreground arrival/reconnect, persistent history and cross-platform encrypted export/import. | Real provider background delivery in the available native testing environments, complete hosted recovery and final signed release builds. |
| Continuous immersion | Stable inline flips; curated English↔Arabic/Japanese/Korean/Chinese interactions; mixed playback; script/reading controls. | Broad conversational meaning, content depth, sustainable progression, pronunciation and accessibility. |
| Live text size | Android `9a39686` preserves the real conversation across Activity recreation. Apple `70c6af4` preserves latest/older anchors through actual large→maximum→large changes. | Complete accessibility audit; scoped fixes are not blanket acceptance. |
| Lookup routing | Both native paths accepted. Approved partials make zero automatic readiness/translation/alignment calls. Android explicit full makes one actual translation call; repeat makes zero. Cancellation, independent rows, caching and visible recovery qualified. | Apple full translation remains unsupported in this simulator; injected full success is separate evidence. |
| Language data | All 110 directions now have pinned finite source contexts. English→Japanese retains 197 starter entries and English→Swahili 237; both retain 41 additional source-context patterns. Both default native engines produce the same sparse output on the fresh conversation sample. | Useful conversational coverage, Apple persistence, progression and contextual safeguards. The 82-concept extension is a private candidate, not shipped coverage. |
| Full readings | Default Chinese, Japanese and Korean guides have scoped native app/cache/UI qualification on both clients. Original script, immutable copy and original-script speech remain separate from the guide. | Arabic coverage, broader contextual correctness, API28, acoustic verification and final clean-source release qualification. |
| Signed packs | Apple ten native cases passed. Android ten cases plus two actual framework silent-failure controls passed. One authoritative record, checked durability, reopen/corruption checks and truthful cleanup state. | Download/update transport and integration with the live bundled formats. The separately pinned bundled source catalogs are active; this does not qualify remote updates. |
| Private deletion | Android `9bcbb17` verifies removal of encrypted base/new/backup files before claiming completion; isolated failure/retry demonstrated. | No implication of a new live-account deletion or provider recovery qualification. |
| Backups | Existing daily controller retains three verified encrypted metadata generations. Authenticated 20-table isolated restore and device-credential invalidation demonstrated. | Reconcile post-snapshot deletion/restrictions, billing/spend and explicit native re-enrollment before reopening a restored service. |
| Store delivery | Explicit `co.fallsoft.vipi` identifier registered with push and IAP. Private Apple app `6832624092` was last recorded as **Mambo Vipi: Language Chat**, Prepare for Submission. Desired name and release metadata are **Vipi**; saving it awaits renewed company authentication. Google Play company access is verified; its Vipi creation form is unsubmitted. Distribution certificate and retained Android upload key exist; release auth guards are qualified. | Real purchases/refunds/push/bot, Google Cloud authentication, final release qualification and upload/review receipts. Development signing previously passed, but the latest native Mac build stopped at signing after the login keychain locked. Distribution signing also remains held on the separate `pbtv58` keychain. No signing retry until that dependency changes. |

The Mac is registered once with the company team and its development profile is
installed and hash-verified. The private iOS-on-Mac app compiled, but its signing
step failed with `errSecInternalComponent`; it has not launched, downloaded a
translation model or produced translation evidence. The existing keychain dialog
was left untouched. Simulator lookup qualification can continue independently
with account signing disabled. See
`qa/release/apple-mac-development-r01/RESULT.md`.

Apple’s actual Sandbox V2 TEST notification passed: successful provider delivery,
verified signature, matching retained event and no entitlement created. The
production URL remains unset. Annual base/Bot mini products and their separate
one-month trials are configured; real purchase/refund/restore remain open. See
`qa/backend/apple-sandbox-notification-r01/receipt.json`.

Apple's background inbox callback now checks the backend's `kind` field rather
than the incompatible `type` field. The actual provider payload matches a shared
native fixture in both APNs environments; nine backend push tests and two real
delegate callback tests pass in the existing iPhone simulator. No live APNs
request was made, and this is not proof of OS background delivery. See
`qa/backend/apple-background-inbox-hint-r01/RESULT.md`.

Offline recovery now has an isolated reconciliation tool with nine passing
synthetic disk-backed tests. It applies restrictive deletion/suspension records,
deactivates devices, invalidates billing freshness, preserves surviving spend and
consumed request IDs, and rolls back conflicts. It creates a separate SQLite
copy and never authorizes reopening. Independent post-snapshot authority,
production PostgreSQL integration and native
re-enrollment remain open; see `qa/backend/service-recovery-r01/README.md` and
its path-handling amendment. No live restore or runtime change was made.

Device Release packaging now preserves all four ML Kit vendor privacy manifests
that CocoaPods omitted from the static frameworks. The actual unsigned build
contains 13 manifests; all nine existing manifests and four upstream copies are
byte-verified. Missing or changed SDK declarations fail before partial copying.
The listing's privacy-policy URL is saved and reload-verified. Final signed
artifact inspection, release-device network observations and the store data
questionnaire remain open; see `qa/release/mlkit-privacy-packaging-r01`.

An opt-in startup recovery hold now keeps API/WebSocket state paths and all
deployed worker entry points from initializing databases/providers. Static
privacy/help/deletion guidance and liveness remain available; readiness fails.
The focused/affected regression passes 101 tests, with four PostgreSQL-only
tests skipped. This requires explicit configuration before startup; it is not
automatic restore detection, a running-process drain or authority to reopen.
No live hold is enabled. See the recovery-hold receipt in the same directory.

## Current language decision

Nine bounded Swahili first-person predicates are now enabled. Both native clients
agree on all 160 default-route outputs and pass 37 authored controls. Two
independent reviews retain no material error in the changed outputs, with a
minor human-object-agreement caveat in one authored control. At .75, strict
useful-message counts rise from 41→42 under the root review and 35→37 under the
independent review; useful depth rises from 6.81%→9.01% and 5.47%→8.04%.
Whole-unit priority also loses some low-density flips, and any-span reach falls
from 67→63 at .25 and 67→66 at .75. These are disclosed tradeoffs on the exposed
80-message lookup-only diagnostic, not broad coverage or native-speaker gold.
The existing 213 records remain unchanged in the 222-entry pack. See
`qa/immersion/positive-predicates-r01/FINAL_RESULT.md` and root acceptance.

The newer ordinary-conversation diagnostic exposes a substantial content-depth
gap. On 80 source messages from separate retained BST VALID conversations, both
native routes produce identical results at two densities. At .75 the baseline
reaches 63 Japanese and 68 Swahili messages with any span, but the independent
reviewer credits useful, strictly compatible content in only 31 and 35 messages.
Correct useful-content depth is about 4.7–6.2% Japanese and 5.5–6.8% Swahili
across the two reviewers. The finite-context patterns contribute no selected
unit in this sample. These measurements isolate lookup with translation-model
availability disabled; they do not measure the complete product with prepared
local translation models. See `qa/immersion/conversation-depth-r01/REVIEWED_RESULT.md`.
This exposed sample is now development evidence, with a retained exposure ledger.

The diagnostic's cat-hair meaning error is corrected by withholding the
unqualified Swahili human-head-hair mapping. Both native default routes agree:
only the two affected density rows change; the other 318 selections stay the
same. Source masks prevent alignment fallback from restoring the withheld
mapping. The retained 213-entry pack changes only this guard; valid human-hair
uses are also withheld. Swahili any-span reach therefore falls to 67/80 in this
diagnostic. See `qa/immersion/contextual-sense-hold-r01/FINAL_RESULT.md` for
qualification, the retained failed Android control and its isolated amendment.

The reviewed source-context increment is now enabled in both clients. Existing exact
and composed full references retain priority; on misses, finite reviewed phrase
contexts add whole units before ordinary starter vocabulary within one budget.
The corrected routing comparison preserves all baseline message matches in the
retained 80-case-per-pair diagnostic, increasing .75 nonempty messages from
54→59 Japanese and 55→58 Swahili. The independently reviewed results and
disagreements remain in `qa/immersion/source-context-frames-r01`.

Both actual default native routes pass all 656 retained comparisons with zero
translation calls and identical selections. Only eight captured Swahili display
faces change by the two documented capitalization corrections. The 41 patterns
and 390 finite variants per pair retain their seed provenance; these are not
population coverage counts. Both default conversation components demonstrate six
fixed-layout flips, Japanese script/readings and Listen reaching playback.
Malformed-pack controls and an Apple shared-provider concurrency check pass;
Android's final reading-type guard has separate targeted binary qualification.
The original Android System UI obstruction and later successful runs remain
separately recorded. The enabled source and four installed pack files match the
qualified copies; their combined size is 106,428 bytes. No customer deployment
or signing retry followed. See `qa/immersion/source-context-frames-r01/FINAL_RESULT.md`
and its root acceptance receipt.

The corrected starter expansion is now enabled: **189 Japanese / 213 Swahili entries**, adding 144 / 107 while preserving all previous records. Demonstrated Apple/Jobs/school sense conflicts are withheld, including plural schools; generic underscore/common-filename preservation prevents vocabulary changes inside technical tokens. Both native default routes pass the final bundle controls, continuous fixed-layout flips, Japanese reading/script display and Listen reaching playback with the new vocabulary. At .75 on the retained 231-source comparison, nonempty messages increase 173→188 Japanese and 192→199 Swahili, with covered native words 336→425 and 448→498. These diagnostic gains are not a 90% population-coverage claim. Both independent reviews retain the original failures and minor disagreements; no corrected candidate output carries their material-error label in this sample. Dictionary notices and full license text are accessible in both clients. See `qa/immersion/starter-content-expansion-r01/FINAL_RESULT.md` and `root-acceptance.json`.

Japanese and Swahili now select several approved, non-overlapping vocabulary units within the existing native word budget, rather than stopping after one. Both native implementations reproduce the reviewed selections across the supported slider range. Actual default conversation components demonstrate three Japanese/four Swahili substitutions, six stable continuous transitions, Japanese reading/script controls and mixed-language playback states. This adds depth to already matched messages; it does not establish broad conversational coverage or learned-vocabulary progression. The retained reviews include minor hair, opinion and wellbeing-expression concerns. See `qa/immersion/starter-packing-density-r01/RESULT.md`.

The earlier 106-entry English→Swahili starter joined Japanese through the default native pair dispatcher before the expansion above. All 384 final selections match across platforms; the prior 384 Japanese selections remain unchanged. Root review records 203 correct, 2 minor and 179 empty state-specific outputs. Both actual conversation components pass six stable source/target transitions, Japanese reading/script controls and Listen reaching playback on the same default-resolved message. These are bounded agent and simulator checks, not broad coverage, acoustic or physical-device acceptance. See `qa/immersion/swahili-starter-promotion-r01`. The existing known-concept input suppresses substitutions; durable learning must use distinct familiarity state rather than persist learned words into that exclusion list.

The earlier English→Japanese starter activated on both clients used a corrected 45-entry version that removed a demonstrated person-name error (`Winter` becoming the season). Its initial qualification produced identical selections over 128 frozen messages at three caller-known states. Only those two name rows changed from the original capture; all 382 other selections were unchanged. Root review counts 187 correct, 8 minor and 189 empty outputs across repeated states. These are diagnostic agent judgments, not population coverage or native-human gold. That initial increment selected one vocabulary unit per message; the subsequently qualified packing policy above lifts that limit while retaining source grammar and Latin-letter readings. Durable learned-vocabulary progression remains open. See `qa/immersion/japanese-starter-promotion-r01/RESULT.md` and root acceptance.

Both native apps now contain an indexed source-phrase candidate engine, still
uncalled by customer presentation. The complete 127 MB catalog retains all
2,556 ordinary and 1,480 conditional heads and their original evidence; the
separate 4.9 MB context pack retains all 1,157 rules, including 23 no-output
winners. Longest-context selection, whole source units, independent source
masks and caller-known vocabulary are preserved. Every result binds to the
exact catalog manifest, catalog, context pack, both dictionaries and policy;
stale text, protection or bundle identity is rejected.

The retained 52-case reference reproduces 145 candidate occurrences and all
312 original selection decisions in both native implementations. Apple actual
observations remain separately recorded: native role/geometry differences can
withhold a candidate, and name detection is imperfect. Its current-tuple wrapper
retains all 50 conditionally qualified occurrences with exact dictionary support.
Android actual candidate/gate/selection fields match the frozen observations on
these 52 records, with one source-mask geometry difference. Its current tuple
evidence also loads, but conditional eligibility remains withheld because the
Android provider has no generic name protection. Neither POS labels nor these
implementation comparisons certify meaning or broad conversation coverage.

Native startup verification now hashes chunks inside autorelease scopes. The
standalone full Mac probe fell from 1.47 GB to 50 MB peak RSS with unchanged
non-timing output; this is not total mobile-app memory. Android's actual main-app
QA package passed on API35, with separate initialization and processing timings.
Physical devices, broader native inputs and final optimized release qualification
remain open. See `qa/immersion/native-candidate-binding-r01/RESULT.md`,
`qa/immersion/native-digest-memory-r01/RESULT.md` and
`qa/immersion/android-candidate-producer-r01/RESULT.md`.

A proposed generic ambiguity gate was tested and rejected: it withheld additive
“too→demasiado” and emphatic “just→Apenas,” but also discarded substantial valid
vocabulary. Dictionary `source_safe=false` largely reflects multiple native
senses, not a wrong translation in the current message. Repeated or dominant
translation counts alone do not resolve intended meaning either. See
`qa/immersion/semantic-admission-gap-r01/RESULT.md`.

The completed eight-message diagnostic used exactly eight installed local full
translations and unchanged native alignment. Neither known wrong focus was
emitted, but only two of six designated valid controls survived (eggs and
definitely). Full translation supplied useful context for here and beauty;
strict dictionary alignment discarded their multiple source analyses before
examining it. Exercise/station additionally exposed number, sentence and sense
evidence limits. Several full translations contained separate meaning errors,
so translation output is not a gold reference. The existing attested target
projection within recomendaría is intentional; it is not arbitrary slicing.

The isolated A/B comparison retained all16 baseline spans and added11 across
the same eight cached targets. All11 additions were independently reviewed as
contextually compatible; here and beauty raise designated-control retention
from2/6 to4/6. Exact baseline parity and synthetic ownership controls passed.
The eight real graphs had no conflicting-owner cases; they do not independently
prove rejection behavior. Full target errors remain separate, and neither this
exposed diagnostic nor the root review is a population benchmark. The source
change remains qualification-only. See
`qa/immersion/target-informed-alignment-r01/RESULT.md`.
The subsequent fixed200-row Taskmaster comparison does **not** qualify B for
activation. Author-reviewed correct nonempty messages rise90→113, but material
error cases rise6→11; all11 lost spans were valid. Root's predetermined40-case
masked review independently observes18→24 correct messages and a new travel
“drive→disco” error. All bad faces were already in the captured ML Kit targets.
Exact lexical ownership cannot establish contextual sense. A subsequent actual
native-role capture preserves all200 geometries but would catch none of the11
flagged scopes: all four assistance uses are tagged Verb, and the same-POS
errors remain. A strict POS filter would instead reject13 author-correct and
three minor selected spans. It is not being added. See
`qa/immersion/taskmaster-source-roles-r01/RESULT.md`. The original14 null
targets remain in every denominator. This historically exposed corpus is not
fresh bilingual gold. See `qa/immersion/target-informed-taskmaster-r01/RESULT.md`
and `CAUSAL_INSPECTION.md`; no candidate policy is active.

The retained Apertium stack has now processed all200 sources through morphology,
HMM tagging, lexical selection and structural transfer, stopping before surface
generation. Its noun analysis exposes the four assistance-help conflicts, but a
strict role veto would also exclude nine author-correct and five minor B spans.
The two actual contextual lexical changes concern room/address; none repairs
the flagged same-POS errors. Different dictionary defaults and generic noun
chunks are not contextual meaning proof. The experiment adds no engine or
policy to the apps. See `qa/immersion/taskmaster-structural-evidence-r01/RESULT.md`.

The unchanged companion producer was also run on all200 original sources with
no target texts supplied. It yields61 nonempty messages, versus133 from retained
target-informed B. Author review finds40 correct,15 minor,5 material and1
uncertain companion output. Its five material additions come from ordinary
heads (movie trailer/caravan, additive too, a place-name number and meal course),
so conditional noun exceptions are not their cause. This is not overall app
coverage:21 producer-empty rows already have exact whole authored references in
the separate app route. All27 bound artifacts and both frozen reviews are
retained. No activation follows; see
`qa/immersion/taskmaster-source-first-r01/RESULT.md`.

The current routing also distinguishes full translation requested for an already
accepted partial: it attaches the target sentence without rechecking its spans.
No new research catalog or semantic exception is active. Conversation-level
sense selection, useful coverage across directions and sustainable progression
remain unqualified.

The latest comparisons establish these limits:

The completed context expansion removes the 5,000-key multiword cap while retaining
the 3,000 single-word entries and the same 40,000 Tatoeba pairs. It finds 19,470
additional contexts matching the retained 9,535 native TRAIN messages.
Four-to-eight-word matches reach 3,117 messages versus 1,595; any-length matches
remain at 9,506. With the same alignment, head/role rules and 25% budget, raw
nonempty outputs increase from 4,398 to 4,557, or 2,729 to 2,876 when the first
300 vocabulary families are withheld. Both independently frozen reviews agree
on all 46 emitted units in 24 stratified changed-output cases. Strictly correct
nonempty outputs increase 12→17, but decline 12→10 among the 16 cases already
nonempty in both arms. Longer contexts repair one additive “too” error but
introduce a university/school mismatch and form defects; “just as” remains wrong.
These reused TRAIN counts are not population accuracy or correct coverage.
The completed evidence is retained; no catalog was activated. See
`qa/immersion/context-key-expansion-r01`.

Read-only loss accounting narrows the next investigation. In the expanded arm,
9,411 messages have a shared dictionary head in a matched context, but only
6,221 have an eligible form/sense/POS/number link. Of the 3,190 messages first
lost there, 2,971 still contain exact native words tagged noun/adjective/adverb;
whole-utterance POS exclusion is not the main explanation. These are potential
content words, not verified meanings, and grammatical adverbs may still be
classified as function words. The next probe inspects concrete source forms,
target links and corpus witnesses. Raising density does not resolve this loss:
all 4,557 messages with an admitted candidate already receive a selected word.
No guard was relaxed, and no recoverable-correctness claim follows from these
counts. See the two `loss-accounting` reports in the same directory.

A subsequent frozen twelve-message probe includes 31 words the existing
classifier calls content: eight lack a retained covering context, seven lack a
shared focus link in the top witnesses, and sixteen have rejected links. All
have a complete supported source form. Root found that a global source name
flag blocks ordinary boys/chat/mom/family/parks/dog uses despite otherwise
eligible noun links. The completed narrow common-noun comparison requires actual
lowercase NOUN usage and preserves target guards and every other restriction.
Raw nonempty output rises 4,557→5,855, or 2,876→3,468 with 300 content families
withheld. Both independent reviews find 26 correct added emissions and three
materially wrong additions in the 24 sampled changes: seasonal “fall” becomes
“caída,” and “Dragon Ball Z” is split into translated common nouns. Strictly
correct whole outputs increase 6→17 in this deliberately changed sample, not a
population accuracy estimate. One retained financial-idiom judgment differs
between reviewers and remains unresolved. The twelve exposed diagnostic sources
are separate controls: seven of their 24 state-specific outputs gain correct
immersion; “amazon and costco” remains unchanged. No runtime exception is active.
See `qa/immersion/source-name-scope-r01/RESULT.md`.

The completed follow-up checks all 1,480 newly eligible heads and preserves all
29 sampled additions. Only 91 heads have multiple casefolded target faces under
the diagnostic rules; 43 have two faces each supported by at least two corpus
components. Those are availability counts, not correct training labels. Raw
unigram evidence includes autumn's “otoño,” but the current qualifying noun-link
path omits it. Conversely, that path admits a verbal “order→pedido” occurrence
as noun evidence. The title has no retained covering context or spanning mask.
All 761 detailed audit rows reconstruct exactly against their 28 head aggregates,
including source/pair/component counts and deduplicated local-context features.
The retained dictionary trace now identifies the missing seasonal relation:
Spanish otoño explicitly glosses “autumn, fall,” but the builder drops fall
because two English noun entries pass its uniqueness check. The season is a
sense of entry 15812; the separate zero-term entry 15814 means whale hunting.
Changing the explicit-link flag alone cannot recover this omitted relation.
The trace covers all 110 noun forms from the 29 additions and retains the
different causes behind the 17 zero-term forms. The next experiment preserves
direct spelling/POS candidates without inventing a unique English sense, then
qualifies source and target occurrence roles before fitting contextual rules.
No catalog or classifier was activated. See
`qa/immersion/lexical-choice-evidence-r01/RESULT.md` and
`qa/immersion/lexical-relation-provenance-r01/RESULT.md`.

The first bilingual occurrence-role qualification is complete. Two independent
pre-inference reviews agree on all 80 focus-token roles in 32 frozen parallel
pairs. OpenNLP matches 37/39 English and 39/41 Spanish focus roles, with no
false noun rejections among the 63 reference nouns. However, it labels the
Spanish verbs pediste and llamas as nouns. In “Your name is Tom” / “Te llamas
Tom,” a noun requirement on both sides would still admit the wrong word-level
mapping. Those diagnostic results support treating tags as evidence rather than
semantic approval. The same retained dictionary trace now serializes 17 direct
English spelling/POS candidates without selecting a source sense; packed terms
remain unchanged. See
`qa/immersion/bilingual-occurrence-roles-r01/RESULT.md`.

The retained Apertium morphology/HMM comparison now correctly resolves pediste,
llamas and Tom on those same frozen examples. All 74 exactly mapped focus tokens
match both reviews, including all 63 reference nouns. Six name tokens remain
unassessable at the original token granularity: two recognized multiword place
names and Fisher, which is unknown on both sides. Root verified the raw stage
streams, exact spans and all comparison counts. This supports complementary
occurrence evidence, not population accuracy or same-POS lexical selection.
See
`qa/immersion/apertium-occurrence-roles-r01/RESULT.md`.

The larger frozen pass is now complete: 14,004 full endpoints, 131,705 tokens
and all 12,500 head-observation joins. Annotation took 88.2 seconds; the completed
join took 147.0 seconds and retains 313 MB of provenance on production. Every
legacy alternative and independent occurrence/component identity reproduces
exactly. Requiring noun roles on both exact forms retains 1,335 of 1,480 heads
and 5,090 of 5,857 source occurrences. Existing alignment/mask restrictions
then retain 1,334 heads and 4,426 occurrences. These are evidence-availability
counts, not correct conversational coverage.

Root inspected all five retained fall/order diagnostic witnesses. Two support
seasonal fall→otoño; a third discusses the quoted word “fall” itself and has
blocked alignment. The role evidence distinguishes nominal “Here's your order”
from verbal “I did not order this.” The direct seasonal relation still has no
resolved English sense identity. No app catalog was activated. The next bounded
comparison tested default translation frequency against local and whole-sentence
context with component-separated evaluation and independent agent review of
complete mixed outputs. These reviews are not native-speaker certification. See
`qa/immersion/apertium-corpus-evidence-r01/RESULT.md`.

That frozen comparison did not establish a better selector. On 201 held-out
occurrences with multiple supported training targets, corpus-target agreement
is 172 for default frequency, 170 for nearby context and 164 for full-sentence
context. This surrogate penalizes some valid synonyms. Both independent reviews
instead find 14/16 strictly acceptable full mixed outputs for every method in
the stratified sample. Sentence context fixes an offspring/young-audience error
but introduces a technical collection-word defect; reviewers disagree only on
that defect's severity. Duplicate normalized sentence text does not cross the
training/evaluation split. No classifier is promoted. The next experiment
isolated the existing Apertium lexical-selection rules from its bilingual
default and full grammar transfer. See
`qa/immersion/contextual-lexical-selection-r01/RESULT.md`.

That existing-rule comparison is also complete. Across the same 781 noun focuses,
the shipped rules change no first choices. Six rules do reduce alternative lists;
the rule asset is nonempty. Exact position mapping and training-supported forms
produce 555 provisional faces, of which 524 have exact morphology support;
31 remain unqualified. There are no new changed cases for semantic review.
This result concerns this common-noun cohort and does not establish a general
limit of Apertium. Nothing was activated. See
`qa/immersion/apertium-lexical-selection-r01/RESULT.md`.

The longest-first learned context lookup is now complete on the same frozen
data. It compiles 30 rules into a 270,164-byte table including support metadata.
The adjacent/centered arm matches no test case; the wider arm changes three
of 781 choices. Two use noncentral three-token contexts and one uses four
tokens. Both agents accept all ten anonymous options in seven complete-message
cases, so these synonym changes establish no semantic improvement. Root saw
some parallel references before freezing; only the author review is also
reference-blind. No five-to-eight-token rule met the fixed support threshold.
Root independently reconstructed the 11,848 patterns, source annotations and
all 2,343 method choices. No catalog is activated. See
`qa/immersion/context-rule-lookup-r01/RESULT.md`.

The retained-data inventory now confirms 40,000 Tatoeba English–Spanish,
40,000 PGV English–Spanish and 20,000 PGV English–Swahili pairs. Existing
annotations contain 24,177 potential English content-role occurrences across
nouns, verbs, adjectives and adverbs, beyond the prior narrow noun pool. These
are not yet linked or approved substitutions, and the selected 7,115-pair
annotation cohort remains biased. Swahili has a smaller retained dictionary and no qualified live source-role
route; it cannot inherit Spanish validation. See
`qa/immersion/coverage-expansion-inventory-r01/RESULT.md`.

The complete-form preflight has now counted 260,900 prospective relations across
those 7,115 pairs without building another proof database. Existing restrictions
leave 1,350 noun, 442 adjective and 259 adverb source occurrences clear of the
legacy checks; none of the verbs passes, and these counts are neither approved
outputs nor gains over the baseline. The projected evidence would add about
854 MB of logical objects/index data. Bulk materialization remains deferred. The bounded context-qualified noun
comparison below has completed; broader verb/adjective policies remain proposals.
See `qa/immersion/ordinary-content-preflight-r01/RESULT.md`.

That context-qualified comparison recovers ordinary nouns in 531 additional
messages, or 143 after withholding the first 300 vocabulary families. Nonempty
outputs become 5,088/3,019 of the same reused 9,535 TRAIN messages. Both blind
agent reviews accept all 18 sampled additions over the baseline. However, the
gate also removes nine accepted sample emissions relative to the unrestricted
exception, and inherited non-noun errors remain. The older seasonal fall and
Dragon Ball Z errors are withheld, not translated correctly. Overall emitted
word depth remains only 7,376/3,700 of 121,960 native words. Root independently
reconstructed every competing training face and support set for the 1,157
qualified rules; original controls and full decision fields reproduced exactly.
The 28 stratified sampled cases and 24 exposed controls do not establish
population accuracy. No research catalog is activated. See
`qa/immersion/context-qualified-nouns-r01/RESULT.md`.

The next compact adverb-support preparation found 17 qualified contexts from
120 training focuses. They match 177 native focuses, all already represented
in the candidate baseline: zero novel vocabulary or message coverage. The
experiment stopped before projection, with no policy relaxation or activation.
See `qa/immersion/ordinary-adverb-contexts-r01/RESULT.md`.

| Approach | Observed result | Decision |
|---|---|---|
| Exact phrase windows, finite slots and typed possessors | Actual Swift/Kotlin agree on the frozen authored examples. The ten-family catalog recognizes only 54 of 9,535 reused TRAIN messages; typed slots add no TRAIN reach. | Keep the mechanism; small template catalogs do not solve broad coverage. |
| Automatically aligned corpus phrases | A frozen 60,000-pair English–Spanish/Swahili build produces thousands of phrase proposals, but independent contextual reviews find wrong senses, omitted predicates and imported words/persons. | Corpus frequency and alignment are candidate evidence, not semantic approval. |
| Dictionary-corroborated complete units | At 25% density, raw content appears in 6,872 Swahili and 8,865 Spanish messages out of 9,535. All three reviewers accept 14 of 16 nominated scopes; title handling and musical play still fail. | Promising breadth; needs actual source-context selection. These counts are not correct-immersion coverage. |
| Dictionary-backed heads within corpus contexts | All three reviewers accept 16 of 16 nominated scopes, but a different selected word in one reviewed message uses a noun for verbal visit. Raw content reach is only 1,719/4,630 messages. | Bilingual dictionary POS agreement does not prove the word's role in the current sentence. Most proposals match only a single-word context. |
| Heads combined with the earlier editorial candidate | All three reviewers accept 15 of 16 nominated scopes; degree too is still confused with also. | No complete candidate accepted. Whole-path errors and later-learning depth remain gates. |
| HFST/lexd Swahili morphology | Actual isolated compilation/query succeeds with small analyzer/generator files, but common words and some negative/person forms fail. | Possible build-time evidence; no general generator or native dependency adopted. |
| Apertium English–Spanish transfer | Actual stage capture handles possessive birthdays and noun/verb book, but fails country musician, on my way and other ordinary contexts. | Useful morphology/tagging/transfer components, not a complete meaning authority. |

Actual source-annotation probes now exercise the same 116 frozen messages with
Apple NLTagger in the existing macOS VM and OpenNLP 2.5.10/English UD-EWT on the
existing Linux JVM. Against 52 independently frozen nominated role expectations,
Apple matches 51 and OpenNLP 49; different mistakes remain. OpenNLP labels the
noun planes as a verb with a raw score of 0.98, so confidence cannot substitute
for qualification. Both recognize verbal visit, but POS does not resolve musical
play, degree/additive too, titles or all personal names. These selected reused
cases are not population accuracy or an Android runtime qualification. Original
text/ranges and repeated OpenNLP output are verified. See
`qa/immersion/native-source-annotations-r01`.

The same inventory retains supported Spanish alternatives for musical play,
verbal visit and degree/additive too. Swahili has no musical-play verb in this
frozen corpus pool. Some dictionary sense links also disagree with the actual
aligned occurrence's grammatical role. A selector cannot repair absent evidence
or treat a dictionary link as a training label without occurrence checks.
The completed sense-agreement analysis was too restrictive to serve as the main
lookup strategy. It covered only explicitly linked pivot senses, and hundreds
of keys also had eligible direct-English links outside that subset. It did not
establish agreement across every source meaning. The negative result is retained;
another strict all-sense gate is not the next step.

The next completed experiment annotated all 9,535 sources with actual Apple
NLTagger and OpenNLP, then compared six fixed-pool selection policies at 25%
density and five known-vocabulary states. All 95,350 original decisions were
reproduced exactly before filtering. Three independent reviews cover every one
of 77 displayed scopes across 32 complete messages, including newly selected
replacements after filtering frees the immersion budget. Each reviewer found
21/32 nonempty whole outputs acceptable with minor issues tolerated in the
original arm, 22/32 after dictionary eligibility checks, 26/32 with Apple role
required and 23/32 with OpenNLP role required. These are selected diagnostic
cases, not population accuracy; strict judgments and utility classifications
differ. Empty outputs earn no pass. Original labels and disagreements remain in
`qa/immersion/source-role-veto-r01/comparison.md` and its linked receipts.

Occurrence roles remove real noun/verb errors but can also reject valid
substitutions. A role-compatible target can still have the wrong sense, and a
newly selected replacement can introduce another error. Neither policy is
activated as a semantic acceptance gate. Apple role-required raw content reach
is 5,933 Swahili and 8,197 Spanish messages, falling to 2,685 and 5,539 after the
simulated function-plus-300 known state. These are match counts, not correct
coverage. The broad source annotations use the existing macOS VM and a JVM.
OpenNLP has since passed a separate actual Android API 35 x86_64 qualification:
148 source messages, three repeated passes, and exact JVM tags, UTF-16 ranges
and scores in both debug and genuinely optimized R8 builds. Both qualification
packages lack Internet permission and use the pinned local model assets.
The 1.66 MB release qualification APK is not the size of the complete Vipi app.
API 28, ARM64, physical-phone performance and integration into Vipi's normal
conversation path remain open. This component result does not approve its
semantic decisions; see `qa/immersion/android-opennlp-runtime-r01/qualification.json`.

Observed debug model loading took 28 seconds and the later release load took
0.418 seconds under different boot/cache/JIT and concurrent-build conditions;
this is not an R8 speedup or cold-start guarantee. Release passes over 148
messages took 384–494 ms including JSON, file output and instrumentation
transport. Process memory includes that instrumentation; neither model-resident
memory nor a leak was established. No further run was needed for this scoped
functional result. Original failed and stopped attempts, exact artifacts and
closure receipts are preserved; the isolated package was removed and only the
owned emulator was stopped.

A follow-up compares withholding catalog-function units using already computed
outputs for 16 of those messages. All 96 prior outputs match exactly, and the
48 reviewed units are unchanged; no selector or model ran again. The two
reviewers preserve their previous labels and reread every resulting output.
Nonempty whole passes move from 14 to 13 for Apple role-required and from 10 to
12 for OpenNLP role-required. Withholding removes errors but also valid content,
and empties useful messages. Wrong construction choices in “keep appointments”
and “touch-ups” remain; the catalog also misclassifies some grammatical words as
content. This supports an explicit native-grammar product policy, not blanket
activation of the current catalog filter. It supplies no new coverage or fresh
independent semantic evidence. See
`qa/immersion/function-withheld-comparison-r01/comparison.md`.

The corpus comparison uses retained native token geometry and 9,535 reused
TRAIN messages at three immersion densities and five simulated vocabulary
states. It makes no translation-provider calls. Its 96-case review is a
stratified diagnostic, not population accuracy or certified bilingual gold.
The three reviews were frozen independently. Original disagreements remain:
minor form/number/degree differences are not silently promoted to perfect
translations. The raw phrase arms also use historical containment restrictions,
which are weaker than the native exact permission contract; their outputs are
not native-admission qualification.

Learning depth remains important. After function vocabulary and 300 frequent
content families are simulated known, dictionary-corroborated content reach
falls to 3,181 Swahili and 6,235 Spanish messages. This is source-vocabulary
exhaustion, not a demonstrated user learning model. A large file or a high raw
match rate cannot establish sustained accurate immersion. The next comparison
must address contextual senses and complete constructions beyond the completed
role-filter comparison, with separate matched-context and display ranges. Do not
replace this with another small list of hand-picked word fixes. The retained
Tatoeba corpus has now been recovered through the existing Storage Box route.
The exact temporary copy and a frozen subset of 40,000 direct development
English–Spanish pairs passed independent provenance, exclusion and token-span
checks. No subset full text overlaps the retained PGV control. The sentences
average about eight tokens, compared with about 21 English tokens in PGV;
contributor and sentence-family concentration remain explicit limitations.
The single frozen alignment and phrase extraction completed in 6.29 and 27.49
seconds. Tatoeba supplies candidates for 5,816 of the same 8,000 source keys,
versus 5,752 for PGV, with 164 versus 72 four-to-eight-word keys. The frozen
32-proposal review finds incomplete constructions and wrong predicate mapping;
it does not establish a usable-output quality winner. Reviewer differences and
unchanged cognates are retained explicitly. No catalog is activated. The separate
Swahili supplement still needs an exact source route. See
`qa/immersion/tatoeba-domain-comparison-r01`.

Japanese native tokenization is now qualified as a research prerequisite:
36 inputs reconstruct exactly, one oversized input rejects as expected, and
warm output is stable. It is not a Japanese corpus or translation qualification.
The completed comparison details are under
`qa/immersion/nlp-template-comparison-r01`,
`qa/immersion/corpus-phrase-extraction-r01`,
`qa/immersion/hfst-morphology-feasibility-r01`, and
`qa/immersion/apertium-transfer-feasibility-r01`.

Earlier word/phrase, source-role and dictionary-expansion results remain in
`qa/immersion/coverage_ceiling_experiment` and private immutable review receipts.
They include material compound/idiom mistakes and insufficient depth after
common vocabulary is learned. The previously untouched BST TEST contexts have
already been consumed; reuse is diagnostic, not fresh acceptance evidence.
No new pack, 90% multilingual coverage claim or all-language release is accepted.

The bounded conversation cache now retains deterministic rejected local-provider
outcomes for automatic reentry. Explicit retry and observed model-readiness
changes permit another attempt. Useful partials, transient failures, source
errors and stale responses remain separate. Android's installed Japanese models
reproduced three calls for three automatic requests before the fix and one
afterward. Apple's actual coordinator qualified the same lifecycle with injected
retained responses, not fresh Apple translation. Identifier checks are unchanged.

## Native full-reading work

Complete readings prefer authored references; the normal Apple and Android
sources now include scoped qualified Chinese, Japanese and Korean guides.
Arabic full-text reading remains incomplete. Audio remains the pronunciation
authority. A valid orthographic convention must not be mistaken for an acoustic
error or described as a verified ordinary pronunciation guide.

Chinese candidate `d6181e0` uses reproducibly exported MIT-licensed pinyin-pro
data with a native Swift implementation. All 332 cases preserve source pieces
and match the pinned upstream mechanically. Root's corrected 80-case review
has 72 readable, four guarded abstentions, two context-limited standalone forms
and two syllable errors. The informed full review retains ten syllable errors,
including eight of 200 reused conversational messages. These are agent reviews,
not fresh population accuracy. Root's earlier label calling `睡觉→shui jiao`
wrong was corrected and the original review retained. A general maximum-input
fix reduced the observed worst mixed probe from 4.9 seconds to 81 ms on the VM;
it is not a physical-device latency guarantee. Broad CC-CEDICT augmentation and
a separate small neural reader introduced regressions and were not adopted.

Japanese `6ccba15` combines existing Kuromoji readings with a native kana chart
converter and exact literal/source guards. The cross-token gemination defect
is corrected. All 270 repeated sentence outputs are stable and all 100 reused
corpus messages have a candidate, but known Han/context errors remain; complete
output is not complete correctness. The new converter removes its dependency
on the API-29 ICU Romanizer, while API-28 execution is still untested. A measured
quadratic URL-tail path was replaced by one delimiter pass in `2bb2f99`, retaining
the prior output hashes. The eight-case gated Android chat check passed on the existing API 35 runtime
in `10bc065`, including authored precedence, cache reentry, exact original copy
and actual original-script speech. It retains the known `一人→ichinin` reading
error, and separately records real local-translation errors in names and a
snake sentence. Candidate availability does not establish translation quality.
The practical authored-first guide policy is now accepted for Japanese and
Korean as well as Chinese, conditional on actual default packaging/cache checks.
Android is qualifying that integration. Known contextual reading errors remain
visible in the evidence; a perfect-phonetics requirement is not a rollout gate.

Android `4df1d63` moves authored readings off the rendering path into a bounded,
coalescing cache. Seven cache/Compose cases plus an actual ChatScreens history
case passed on API 35. Delayed reading grew from 71 to 142 pixels while its top
stayed at 761 pixels and the older-history position remained stable. This uses
synthetic transport and authored data, not a live translation-provider result.
Apple `4c4457b` passed a normal app build, three native coordinator cases and one
gated large-text display case after verified storage recovery. Metadata does not
block completed script/audio or another row; closed identities reject late
completion. These use supplied/injected translation results. Actual production
history growth subsequently passed: an authored reading expanded from 130.33 to
197.33 points while its top stayed at 205.611 points and the older-history
viewport remained unchanged. `a740091` then passed the normal bundled Chinese
reader with its exact 773,812-byte data and MIT notice, three coordinator tests
and two UI tests. No QA enable flag or copied QA data was required. Root verified
14 source hashes and five frames. These supplied-target simulator checks remain
separate from actual Apple translation. The shared receipt-name collision was
corrected in `759764a`, preserving Apple's original receipt bytes.

Korean retained output follows a documented spelling-based convention permitted
by NIKL, so differences from pronunciation-based romanization are not inherently
errors. The Swift guard and a standalone Kotlin port of pinned Unicode CLDR
letter rules are qualified on frozen inputs; no new pronunciation model is
required. Thirty-one of 32 strings agree across platforms; the maximum-length
case differs only in spaces between native tokenizer runs. Android subsequently
passed the 32 inputs plus six boundary/resource controls on its actual runtime.
Apple's actual simulator capture also matched all32 macOS results. Default
integration is accepted in Apple `7d90c4f` and Android `f73bde5`, including scoped
actual chat/cache cases. Android default Chinese `05e52f0` then matched all332
Swift cases and passed its actual chat controls. Apple Japanese `5422153`
matched all32 frozen macOS outputs and passed default-cache and large-text chat
checks. Supplied/injected target text and missing translation models remain
explicit; no acoustic or physical acceptance is inferred.

Arabic research compared three small offline diacritizers on forty fixed
authored/reused inputs. Sizes range from 2.47 to 22.28 MB, with observed desktop
per-sentence times below 8 ms after loading. Common lexical errors, ambiguity,
supplied-vowel overwrites and literal-preservation problems remain. No model is
promoted; see `qa/immersion/arabic-diacritization-r01`. Native packaging,
ordinary Latin conversion and pronunciation are separate gates. Full-reader
metadata must not delay original script, chat interaction or original audio.

The proposed Android contextual message menu remains disabled. The retained
main app now passes a scoped Japanese interaction sequence: exact original
copy, native selection/copy of visible mixed text, Menu and Shift+F10/Escape,
native audio start, reachable stop control, and report confirmation without
submission. Test corrections account for the separate floating-toolbar window,
screen coordinates, clipboard completion and restored focus. Later test-only
probes verified denial and dismissal of Android Accessibility Suite's notification
prompt. The installed TalkBack actions shortcut still did not expose its
service-owned menu; the unobstructed failure frame shows TalkBack focus on the
chat. The cause remains unqualified, and the Arabic sequence was not run. Root
restored all settings and permission state, verified the original app/test hashes
and stopped only the owned emulator. The later harness overlays remain private;
the canonical test stays at the previously reviewed r102 source. Playback
stopped-state and acoustic quality are not established.
The existing accessible action button remains available.

## Resource and external gates

New Apple work belongs on the native Mac. The migration owner verified the old
development VM shut down at 2026-11-09 00:19:52 UTC, completed preservation and
retired its exact backing disk at 01:17:27 UTC. The verified retirement reclaimed
about 112 GB; the guest must not be recreated. A clean native mirror now contains
all 351 committed Apple source files at `a330fdc`; its native core package passed
105 XCTest and 26 Swift Testing cases. All app inputs and pinned dependencies
have since been restored and verified, and the complete arm64 Simulator app/test
build passed. Six selected simulator UI/crypto tests also passed with no skips:
continuous stable-geometry flips, Swahili in both roles, Chinese/Japanese/Korean
reading views and peer-key replacement. Those authored UI fixtures do not
establish broad language meaning or physical-device behavior. Root reviewed
seven selected frames and restored the original simulator preferences while
preserving the private-speech generation counter and existing data. Five UI
cases carry an internal thread-priority warning whose origin and production
impact remain undiagnosed; this is not performance acceptance. See
`qa/apple/native-simulator-20261109-r01/qualification.json`.
Native builds preserve
at least 1 GiB physical headroom plus measured operation size; full source
builds and model preparation require their own capacity checks. Historical guest
model thresholds and small-build exceptions do not qualify native model
readiness. Preserve native projects, accounts and unrelated applications. A fresh
bounded Pixel connection attempt found neither authorized USB nor verified TCP
access, and native CoreDevice lists both paired Apple devices as unavailable.
The existing iPhone simulator remains booted; no new physical test is claimed.

Actual native Mac Translation now succeeds for three authored intents across
English↔Spanish/Japanese/Chinese. Low-latency and platform-default executions
produce identical full sentences and 29 isolated-word outputs per run. Root's
review finds the six full sentences meaning-preserving in these ordinary
contexts, while isolated forms still include noun-for-verb and particle/sense
errors. Swahili is unsupported by the checked Apple strategies; its ML Kit path
is separate. No model download occurred. Networking remained enabled, and these
small macOS CLI runs establish neither offline-isolation nor physical iOS or
general language acceptance. See `qa/immersion/native-mac-translation-20261109-r01`.

Fresh hosted Apple reauthentication stopped at a generic confirmation-code
screen. Bounded WorkOS admin lookup found no matching code event. No renewed
authentication or same-device registration is credited; earlier real PKCE and
refresh results remain valid. No retry, code guessing or provider policy change
is underway.

The native signed-in Chrome profile now verifies `arjun@fallsoft.co`, Fallible
Software, Co., team `3TNL2455JT`. Native AppleEvents succeeded after the earlier
CDP transport failures; shared services and browser profiles were preserved.
The explicit `co.fallsoft.vipi` identifier has push and in-app purchase capability.
Private iOS app `6832624092` is **Mambo Vipi: Language Chat**, version 1.0,
Prepare for Submission. Both shorter names were rejected as unavailable; each
attempt was reconciled before the next. No build upload, review submission or
public availability follows from creating this record.

App Store profile `Vipi App Store 2026-11-09` is now installed on the native Mac.
Its decoded entitlements bind `co.fallsoft.vipi` to the company team, production
push and distribution signing, with debugging disabled and no device list. Its
certificate matches the existing available company distribution identity and
expires September 24, 2027. This verifies signing prerequisites, not a signed
release artifact or upload. The clean device Release build at `6063b0c`
compiled with the production WorkOS identifier and pinned device dependencies,
but archive signing failed with `errSecInternalComponent`. Both keychains were initially observed locked through SSH. A later interactive check found the login keychain unlocked, but the signing retry still prompted for locked `pbtv58`, even with the login keychain explicitly selected. The exact owned build/codesign processes were stopped; no password or keychain configuration was changed. Both failures and outputs are retained; no signed archive or upload is credited.

Vipi-only production APNs key `H8D2H8HN35` is registered, downloaded once,
cryptographically checked and retained in protected native/production credential
storage. The saved portal configuration confirms only `co.fallsoft.vipi`,
production environment. Existing team keys remain untouched. No backend
configuration/restart or physical push-delivery qualification follows from this
credential preparation.

Google Cloud, AWS and the existing DeepSeek company credential requests remain
pending. Do not repeat those unchanged questions. Independent authorized
qualification and private store preparation continue.

The private Apple subscription records are configured: `vipi.base.annual`
($12 USD/year) and `vipi.botmini.annual` ($48 USD/year), each in its own group
with a one-month introductory free trial for eligible subscribers. Localized
prices vary by storefront. Both have English names/descriptions, annual upfront
availability and one-person App Store purchase settings. Store metadata is not
purchase qualification: real transactions, notifications, provider readiness,
release screenshots and review remain open. See
`release/apple-store-configuration.json` for exact identifiers and draft state.

Production WorkOS provider lifecycle now passes real password authentication, pinned-JWKS verification, public-client refresh, rotation and session revocation/rejected refresh on a tagged disposable fixture. Cleanup is verified. Hosted native sign-in, email delivery and live authentication cutover remain separate; see `qa/backend/workos-production-lifecycle-r01/receipt.json`.
