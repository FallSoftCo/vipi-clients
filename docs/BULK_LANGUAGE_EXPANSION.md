# Bulk local language expansion — 2026-10-27

## Current expansion: dictionary 014 plus MASSIVE — 2026-10-28

The complete MASSIVE import retains 181,731 original rows from eleven locales.
After preserving source splits, duplicate components, localization choices,
judgments and evaluation exclusions, it supplies 50,706 development sentences
and 42,596 direct English-to-locale links. Swahili contributes 4,600 development
sentences. This is assistant-request data, not representative friend chat.
No foreign-to-foreign relation is inferred through English.

Source: https://github.com/alexa/massive, pinned repository
f966f21846043aabef9b0f974fa7970027f43738 and archive
4cba5faa11c71437928e17cb1b9b3d8b8e727e7ea363a3a9a8045e19c0491577.
The archive's CC BY 4.0 license, NOTICE, citation and original source payloads
are retained. Import artifacts/massive-corpus-003/corpus.sqlite is 222,208,000
bytes, SHA-256 ef63aefac28e9295ee1002950a4a2062b0124d5c24e188b1b6340cb039af0ff6.
The two stopped partial attempts are recorded separately and are not releases.

The dictionary-014 MASSIVE context build is complete: 319,852,544 bytes,
SHA-256 8ab15b459aea58c08c42b7414a8d1cf1506e941928ad0fd805548306240b269b,
with 144,032 candidate concordances, including 11,077 English–Swahili.
These counts are evidence candidates, not accepted runtime mappings.

The witness compiler now accepts this specific third source only when its
receipt proves exclusion of both prior source corpora and the evaluation
identities. It checks matching dictionary catalogs and disjoint source-ID
intervals, retains attribution and counts contradictory observations in the
same denominators. Targeted checks demonstrate that a third-source conflict
removes a previously supported mapping and that wrong predecessor identities
are rejected. Reserved MASSIVE rows never enter development contexts.

The full Tatoeba/Swahili and PGV context rebuilds are running. The owned
pipeline at artifacts/coverage-expansion-004-run-001 waits for completed
receipts, compiles all 110 directions, creates bundle 004 and runs Android
replay 008. Source hashes are pinned and compiler snapshots execute directly;
a failure stops for inspection. iOS replay and inspection of actual additions
and losses remain required. Bundle 003 remains the currently qualified
development data; bundle 004 is not yet qualified.

Superseded raw dictionary 012 was retired only after all eleven files matched
the retained bundle-003 compressed payloads byte for byte and had no visible
open readers. Exact payloads, catalogs, attribution and provenance remain.
Receipt: artifacts/dictionary-012-retirement-001/receipt.json.


## Swahili lexical source correction in preparation

A targeted native-table audit found 179 published Swahili infinitive links.
The root for kwenda (go) existed only as an unmapped competing analysis in
dictionary 014. The new compiler can follow the exact supplied infinitive
backlink to enda; it does not guess a stem or generate a conjugation.

The same audit exposed derived verbs whose dictionary rows carry form-of
tags despite having explicit meanings such as teach, listen and lend.
The new source policy keeps causative, applicative, stative and reciprocal
verbs distinct from their bases. An explicit source definition can make the
derived verb available as a target; its source side still requires context.
Derivations without definitions remain unavailable and cannot alias their
bases. Ordinary inflection and alias restrictions remain in force.

Artifacts/swahili-infinitive-audit-001 retains exact source rows and the
qualification boundary. The first complete single-language candidate, artifacts/lexical-swahili-015,
was withheld after author review found incorrect homograph links and
unrelated senses in several derived entries. Its comparison and rejection
are retained. Policy 12 additionally requires a unique infinitive backlink
and a direct counterpart or exact label in the derived verb's own definition.
The corrected candidate is building as artifacts/lexical-swahili-016. Both
are separate from bundle 004 and have no native activation; changed-direction
context recomputation and native replay remain required.

## Bundle 003 native development result — 2026-10-28

The dictionary-012 rebuild completed all 110 directions from both retained
corpora. Witness 014 contains 4,815,577 rules; its SHA-256 is
a7a05442cf67057cffdf73fcac97f0f9d7bb3cc40f1bd0e82d56a48c2e7aed73.
The exact 55 bidirectional subsets and 11 dictionaries occupy 352,691,605
compressed bytes, or 1,891,610,624 expanded bytes for all languages.
Only the selected pair is expanded by the app. Bundle catalog SHA:
4859eaa82bc95fe2fa3ce796fa62e700ed8aadb5c737ce3059eada904aca6242.

Both the Android emulator and iOS simulator completed the same 602 inputs
through the real native bundled reader. Each gains 12 spans, loses seven,
and gains nine previously empty ordinary messages. Ordinary message
availability changes from 217/560 to 226/560. This small mixed development
cohort is not a population coverage or accuracy measurement. The two
previous platform selection differences remain.

Author review found the 12 additions plausible in context, including island,
restaurant, family, farm, taxi and game. All seven removals were useful
previous mappings, including book, read and factors; these remain explicit
coverage losses. New contradictory source observations were not discarded
to restore old counts. Whole-translation errors remain, and this does not
establish the 90% goal or store readiness.

Android build 013 passed; replays are bundled-conversations-android-007.json
and bundled-conversations-simulator-006.json. Exact per-span review and
cross-platform differences: artifacts/bundled-lexical-003-qualification.json.
The candidate is active in development assets only. Dictionary 014's larger
adjective correction is the next context build and is not part of this result.

## Supplied adjective agreement and statistical alignment investigation — 2026-10-28

Dictionary 014 additionally makes 214,670 existing surface records usable as
complete adjective forms: Spanish 67,785; French 44,654; Italian 62,255; and
Portuguese 39,976. These represent 119,093 distinct written forms across the
four languages, including ordinary forms such as alérgica. They are not new
words, new translations or an accuracy measurement. Only already supplied
gender/number forms qualify; comparative, superlative, verbal, unknown and
excluded usage features remain unsupported by this correction. No spelling,
stem, reading, sense link or source/target safety flag changes.

The delta is recorded per row in artifacts/lexical-shards-014/changed-surfaces.jsonl.
Release 8efe0921d18ed0c12d82b597f55d7ac65a47196d900435e7620532e1bba7926a
requires fresh contexts and native qualification. The app does not yet use it.
The separate dictionary-012 rebuild is now qualified as bundle 003 above.

A bounded fast_align experiment uses 100,000 English–Spanish and 20,955
English–Swahili direct development pairs, selected deterministically from the
retained contexts. Exact evaluation text was excluded. The tool is pinned to
upstream commit cab1e9aac8d3bb02ff5ae58218d8d225a039fa11 (Apache-2.0);
all training input identities and parameters are retained in
artifacts/statistical-alignment-corpus-001 and statistical-alignment-models-001.
This is a statistical word-alignment experiment, not an app dependency.

The unfiltered mutual alignments produce wrong and incomplete proposals.
A diagnostic probability cutoff plus published dictionary links still gives
laptop → portátil and email → correo where the complete target expressions
are computadora portátil and correo electrónico. It also lacks the native
scope, grammatical-lemma and proper-name safeguards. These proposals are
withheld from runtime integration; they do not establish useful immersion
coverage. Full phrase alignment needs separate investigation. Reports:
artifacts/statistical-alignment-review-001 and -002.

## Noun-gloss correction and complete development directions — 2026-10-28

A subsequent source audit found 1,034 more existing links whose native
definition exactly matches the published translation sense label, but whose
English headword differs. For example, 医者 and the medical sense of doctor
both say “medical doctor.” Two qualified candidates remain excluded.
The compiler's next policy, native-linked-exact-sense-gloss-9, only removes
this contradiction when the complete short, unqualified native gloss matches
the complete sense label. It does not accept other senses of the English
headword. The focused test covers academic-doctor mismatch, mixed meanings,
aliases and qualified definitions. Audit: artifacts/gloss-label-audit-001.
Dictionary 013 applies exactly 1,034 existing eligibility corrections, with no
new forms or lexemes. Its release is
17427cbfa60c44dc017353e2980693ba7a7e6dda7d564d4ff884837bda64d325.
The executed compiler and original catalog are preserved beside a correction
to changed-language metadata: English has zero changed terms. Fresh contexts
and native qualification remain required; active app data is unchanged.


Dictionary 012 corrects a parsing error in short noun definitions: an existing
published counterpart such as island was treated as contradictory when the
native entry said “an island.” Only complete short noun-gloss items gain the
article-free comparison; descriptions, qualified aliases, conflicting senses
and readings retain their existing treatment.

The audit identified 1,798 potentially restorable term links across 1,493
lexemes. The actual full rebuild has 1,795 existing terms changing from
ineligible to eligible, plus 13 term rows added through existing source
relations. It also includes 6,822 additional supplied/indexed surface rows,
primarily Arabic and Korean carriers for entries previously made eligible.
These are dictionary records, not verified conversational substitutions.
Existing lexeme safety flags did not change. Exact per-language differences
are in artifacts/lexical-shards-012/previous-release-comparison.json.

Release 7d9ff2229edea5d194e5db3a7b22dd1a7329aa9af269c16fa4729c098e1ac5af
occupies 1,683,308,544 expanded bytes. All eleven shard hashes and SQLite
checks passed. The temporary 4,428,693,504-byte inventory copy was verified
and retired after the rebuild; the canonical source is preserved. Fresh
Tatoeba and Parallel Global Voices contexts completed all 110 directions.
This revision is activated as development bundle 003; see the native result above.

The retained native development cohort now has 560 ordinary examples and
42 targeted regression examples across all 110 directions. The additional
28 translations into Swahili were captured with the dedicated Android
emulator offline, using already-installed models; iOS replay reused those
exact translations. Both platforms produced substitutions in 217 of the
560 ordinary examples using bundle 002. There are two differing selections
between platforms. This deliberately small, heterogeneous development
sample is not a population coverage estimate, an independent meaning
assessment, or evidence that the 90% goal is met. It includes difficult short
speech fragments and informal SMS alongside assistant questions.

The native replay now records the exact bundled catalog hash and aggregate
selection diagnostics. This distinguishes missing links, competing lexical
analyses and translation identifier changes. The iOS simulator still cannot
run the ML Kit arm64 translator; these results exercise the actual bundled
mapping reader with captured translations. Artifacts:
bundled-development-004, human-prompt-translations-002.json,
bundled-conversations-android-005/006.json, and
bundled-conversations-simulator-004/005.json.


The active expansion uses the full retained dictionaries and direct parallel
text. Storage is a capacity to use, not a reason to limit the catalog to a few
handwritten examples. The development app combines authored starter bundle 022 with broad dictionary
bundle 003. Broader meaning acceptance and production delivery checks remain
open; this is not a store release.

## Changed-language rebuild and actual chat integration — 2026-10-28 UTC

The normal native conversation path uses the broad local dictionary reader.
Chinese dictionary revision 011 restores exact supplied simplified forms and
lexical character entries such as 吃. Character links require an existing
published bilingual relation plus an explicit native gloss counterpart.
Readings remain supplied dictionary data. No Han conversion or guessed stem
was introduced.

The incremental compiler rebuilds all twenty directions involving Chinese from
the pinned Tatoeba and PGV development inputs. It retains negative observations
and the existing minimum-support/agreement rules. The endpoint query now scans
direct links and looks up sentence IDs; it no longer creates an expensive
cross-product of sentence partitions. Unchanged language directions retain their
exact previous witness rows and historical source identities. The recomputation
proof binds the original corpus versions, exclusions and changed dictionary
scope; it rejects omitted directions, dropped source corpora and changed
unaffected lexical relations.

Witness revision 013 contains 4,389,513 rules, including 145,646 newly recomputed
Chinese-direction rules. Its authoring SHA is
7707e3cb4a9c152d895d7b8e16f2eca492bd24edd51404cf94cb9265f8df7a61.
Bundle 002 contains 66 compressed payloads totaling 348,500,118 bytes, or
1,872,195,584 bytes if every SQLite payload were expanded. Only the selected
two dictionaries and their shared context file are expanded on device. These
numbers exclude the starter catalog, translation/voice models and app code.
They are not an App Store/Play download-size measurement.

The development comparison retains the original 334 cases and adds 240 locally
translated cases from 24 human OASST1 prompts in German, Spanish and Brazilian
Portuguese. These are assistant-style public requests, not a representative
friend-chat population. All 240 whole translations were captured on the
dedicated Android emulator with both radios off and without a model-download
call. Median translation time was 171 ms; maximum was 951 ms in this small run.

Android 004 and iOS simulator 003 each select 328 spans across 574 cases, with
all retained positive/negative checks passing. Android gains 13 spans versus
the same 574 inputs on bundle 001 and loses none. Twelve newly selected pairs
have plausible lexical meanings on author inspection. One Spanish weekly-menu
case needs further scope review: the full Chinese translation omitted the menu's
weekly modifier, while retaining a later weekly-training modifier. Whole-message
translation quality is not established by a valid word pair.

The platforms differ on two Chinese cases: Android additionally selects 票/ticket;
iOS additionally selects 今天/Today. Total counts therefore do not establish
exact parity. This iOS run used the simulator with reused translations, not
physical iPad or Apple translator validation. The iPad's OS XCTest passcode
prompt remains unresolved.

New prompt diagnostics on bundle 001 find at least one span in 22/80 German,
41/80 Spanish and 49/80 Portuguese direction-cases. These are small development
samples and include full-translation errors, such as Portuguese dado becoming
English data in a dice question. They do not meet or estimate the 90% goal.

The next measured compiler correction concerns definitional articles:
German Insel's native definition is "an island, an isle". The previous parser
treated those articles as evidence against its existing island link. A narrow
noun-gloss correction and checks are in development; the all-language impact
audit is pending. It is not yet part of bundle 002.

Receipts: artifacts/context-witnesses-013, context-pair-packs-013,
bundled-lexical-002, bundled-development-003,
bundled-lexical-002-development-comparison.json and
bundled-lexical-002-native-comparison.json. The gallery's new chat captures are
bound to earlier bundle 001/build 010 and pass desktop/mobile card checks.
Independent semantic acceptance, broad conversational immersion and store
readiness remain false.

## Priority correction: build useful immersion before broad regression runs

The user rejected treating the large regression count as product progress.
The immediate work is correct, substantial immersion in ordinary conversations:
common vocabulary and phrasing in context, native grammar preserved, readable
transliteration, continuous stable inline flipping and matching local speech.
Run a small fixed development cohort during matcher work; inspect the actual
sentences and selected meanings. Run the broad native suite after a substantial
candidate improvement. Do not report passing mechanics as achieved immersion.

Two Android-only experiments are retained as rejected research (033 and 034).
They use fixture 022: four hash-selected source turns in each of eight existing
dataset/source strata, all existing target directions, and retained observed
semantic failures. The resulting 32 source turns are a development sample,
not an unseen or representative coverage estimate. Its four Swahili turns are
short fragments; no Swahili population inference is justified.

The first experiment aligns complete supplied forms against explicit shared
dictionary senses in the translated sentence, without the old context-witness
requirement. On the 252 non-Swahili conversation-direction cases, selected
spans rise from 123 to 227. This is not accepted progress: it reintroduces six
retained meaning/scope failures and adds a new visible error, noun show in
the 9 pm show mapped to Spanish mostrar (verb). It also consumes grammatical
affixes in some complete carriers. A valid dictionary counterpart plus presence
in a machine translation does not establish the contextual meaning.

The second experiment adds attested lemma keys to both pair lookup and context
cues, requires witnesses for native polysemy, and retains known non-Roman carrier
boundaries. Gains are much smaller (123 to 130 spans in those same cases);
it still accepts French établissement meaning a hotel/institution as Korean
설립 meaning establishment/founding, and loses the required books/libros mapping.
Both experiments are archived outside the normal app source. Their source
snapshots, patch, native outputs and comparisons are under
artifacts/whole-word-development-033-source,
artifacts/whole-word-development-034-source,
artifacts/lexical-coverage-android-033.json and -034.json, and
artifacts/whole-word-development-033-comparison.json and -034-comparison.json.
Neither is promoted. No broad 26k replay or new iPad run was performed for them.

Concrete blockers found:

- Supplied inflections classified as mode 0 cannot enter the existing matcher.
  Examples include Spanish voy/comiendo and French vais/mange. Fixing that
  eligibility alone is insufficient without contextual POS/sense selection
  and exact grammatical-carrier boundaries.
- A compiler bug treats any alternative/form-of sense as invalidating every
  modern lexical sense of an entry. English go has 66 ordinary senses and one
  clipping sense, yet its target eligibility is zero. The compiler now retains
  modern lexical eligibility while keeping mixed entries out of the
  single-sense source shortcut. Pure alias-only entries remain ineligible.
  Verified against native entry 30997 from immutable inventory 003; receipt
  artifacts/mixed-lexeme-eligibility-001.json. Dictionary 009 rebuilt this fix, restoring 8,530 target-eligible lexemes.
  Native dictionary bundles 001/002 now include it; availability still needs
  evaluation in each actual conversation context.
- Some reused native full translations are already semantically wrong.
  For example, an Arabic attraction question is translated as lactation.
  Full-translation quality and vocabulary-selection quality need separate
  review; word matching cannot repair an incorrect sentence by itself.

The next substantive step must address contextual word/phrase selection and
full-translation failures, then demonstrate useful density in actual chat.
Do not repeat tiny guard patches and a full regression run as the main loop.
The current core immersion standard and 90% target remain unmet.

## Native coverage and depth qualification — run 032

Both Android and the attached iPad completed **26,368 cases** against fixture
020, dictionary release 007 and context witnesses 012. The bounded selector
change recovers whole nouns when a competing verbal carrier has different
boundaries, requiring a noun counterpart and nearby lexical evidence. It also
protects spaced **home work/home works** as a complete lexical unit. All prior
accepted baseline spans and retained positive/negative regressions pass.

Compared with Android 028 / iPad 030, each platform adds **20 author-reviewed
spans in 20 messages**, with **14 newly nonempty messages** and no lost spans.
Six newly nonempty messages are SMS cases; eight are reference diagnostics.
These are small coverage gains, not a demonstration of the 90% goal.
Run 031 review found one incorrect generic works fragment inside homework;
032 removes that addition while retaining the valid books mapping.

| Diagnostic | Cases | Android messages with a span | iPad messages with a span |
| --- | ---: | ---: | ---: |
| SMS | 3,600 | 848 (23.56%) | 864 (24.00%) |
| Multi3WOZ | 3,600 | 2,051 (56.97%) | 2,067 (57.42%) |
| XPersona | 2,700 | 1,045 (38.70%) | 1,060 (39.26%) |
| Swahili speech-derived replay | 1,910 | 176 (9.21%) | 180 (9.42%) |
| FLORES human-reference diagnostic | 11,000 | 4,447 (40.43%) | 4,454 (40.49%) |

These are availability diagnostics, not meaning accuracy. All 110 directions
have reference tests, but only 73 have conversational samples. The other 37
remain unmeasured. No direction meets the 90% availability floor in all its
sampled conversational datasets. Full combined outputs differ in 348 cases
between the platforms; this is not exact native parity.

[Immersion coverage acceptance](IMMERSION_COVERAGE_ACCEPTANCE.md) fixes the
denominator and separates availability, native token depth, meaning and learning
outcomes. The new scorecard keeps every input, reports each direction/dataset,
marks missing evidence explicitly and rejects targeted regression fixtures as
coverage populations. Native token ranges distinguish partial carriers from
whole-word coverage. Six accounting tests pass, including surrogate offsets,
zero-coverage messages, missing data and native Unicode classification.

The repeatable missed-word inventory separates grammatical words deliberately
kept native from absent forms and indexed words still needing contextual or
target evidence. Frequent English misses such as eat, coming, finish and watch
already have indexed forms. More dictionary bytes alone will not resolve them.
Author review also records errors in supplied full translations separately
from the correctness of newly selected vocabulary.

Android run 031 was **incomplete**, with 23,301 persisted cases: serializing its
growing JSON report exceeded the test process's 201,326,592-byte Java heap limit.
The QA harness now journals individual outcomes and streams atomic checkpoints;
the runner retains incomplete reports. Full run 032 passed with a maximum sampled
Java heap of 107,310,256 bytes. The iPad's maximum sampled physical footprint was
134,136,912 bytes. These are different memory measures and are not production
memory limits.

Receipts: native qualification artifacts/bulk-native-qualification-032-032.json
(SHA-256 1c0f5ce407bf9979b2792de8de2e9618a179ac6806facb00dae5ee508fbe4962);
review closure artifacts/noun-geometry-review-closure-032.json; per-platform
coverage-scorecard-*-032.json, uncovered-source-inventory-*-032.json and
lexical-coverage-summary-*-032.json under artifacts/. Source snapshot 032 and the
Mac source receipt bind the tested native implementations. Independent semantic
acceptance, majority-chat coverage, production delivery qualification and store
readiness remain false. The app's production language default is unchanged.

## Completed full-corpus expansion

Cumulative witness revision **012** contains **4,314,872 context rules** in
**1,096,957,952 bytes**. Every one of the **110 directed pairs** was recomputed,
including all twenty Swahili directions. Its SHA-256 is
`4cc46543d4a17b9c03a6a0396138c22ebff1095b67db11ace9a30a46f4aba71f`.
Together with the eleven dictionary shards, the full authoring/QA SQLite footprint is
**2,774,634,496 bytes**. A context rule is a word/counterpart/cue combination,
not a distinct vocabulary word, a verified translation or an accuracy result.

The new PGV index covers 2,207,121 eligible development segments, 23,037,495
form occurrences and 11,973,513 candidate alignments. Those alignments are
authoring evidence, not accepted runtime mappings. The cumulative compiler
rebuilds old and new observations together and retains contradictory evidence.
Swahili rules increased from 1,098 to 58,103. The earlier full witness database
contained 1,447,899 rules. Receipts are in `artifacts/cumulative-expansion-001/`
and each immutable `context-witnesses-cumulative-*` directory.

`scripts/expand-context-batches-001.py` is the retained one-shot expansion
driver. It freezes compiler identities, checks every completed build, archives
closed observation databases with verified hashes, and replaces complete pair
scopes. Original archived paths remain usable through verified Storage Box
links. The native runtime still uses indexed SQLite and native selection;
authoring FTS is not a runtime dependency.

### Selective delivery and measured compression

`export_context_pair_packs.py` exports 55 bidirectional SQLite files while
verifying both SQL set differences against the full authoring table. All
4,314,872 witness rows are preserved exactly. The authoring database keeps the
reference/evidence tables; native lookup needs only metadata and witnesses.
The subset catalog binds every file to dictionary release 007 and authoring
witness SHA 012, with source receipt and attribution retained. Export 001 is
**187,703,296 bytes** across all pair packs. The difference from the single
176,287,744-byte witness table includes independent database layout/metadata.

`measure-language-downloads.py` creates ZIP assets and checks the SHA-256 of
every decompressed payload. The eleven dictionaries total **306,296,579 bytes**
compressed; all pair context packs total **40,965,351 bytes**. Together that is
**347,261,930 bytes downloaded**, **1,865,379,840 bytes installed**. This excludes
app binaries, the existing starter catalog and platform translation/voice
models. It is measured ZIP payload size, not a Play/App Store release-size
report. The export and ZIP catalogs are unsigned; production delivery remains
unqualified. No rules were dropped to achieve these sizes.

| Selected pair, both directions | ZIP download MB | Installed SQLite MB |
| --- | ---: | ---: |
| English–Spanish | 121.50 | 615.87 |
| English–French | 86.98 | 350.64 |
| English–Japanese | 68.40 | 249.35 |
| English–Swahili | 57.43 | 211.37 |

MB above is decimal. Shared dictionaries install only once when multiple
languages are selected. The catalogs contain exact sizes/hashes for all pairs.
The working onboarding direction is bundled starter coverage and automatic
selected-pair preparation; see DECISIONS.md for the platform model distinction.

### Native qualification and meaning review

Run 023 passed 15,360 cases on Android and the physical iPad with the
intermediate 101 witness database. It adds exact source-carrier context support:
an Arabic noun can flip while its definite article stays in place. Emoji
offsets, vowel marks, plural mismatch and wrong counterparts are covered.

Run 024 exercised the complete 012 database on both platforms. Both completed
but failed the same newly added experimental positive, `way → camino` in a
literal route example. The larger corpus withdrew the old `R:home` witness;
the implementation must not restore a cue contradicted by new source evidence.
Fixture 015 retains that loss as an explicit `availability_watch` and uses the
still-supported Portuguese literal route as the phrase-guard positive. No
previously accepted primary-catalog positive was removed. This is a corrected
test contract, not repaired Spanish coverage; run 024 remains failed.

Author inspection of 204 changed cases found additional wrong meanings, such
as park management becoming spatial direction, preference becoming better,
and a grammatical nominalizer becoming a job. The exact case identities and
review concerns are retained in
`qa/immersion/expanded_context_semantic_findings.json`. Shared function words
were insufficient evidence for these choices. Native revision 025 requires a
lexical witness when selecting a narrower meaning in the presence of nearby
lexical context. Short grammar-only utterances retain their earlier path.
This remains a conservative heuristic requiring further review, not semantic
certification. Source, fixture and raw run identities remain immutable.

`compare_lexical_replays.py` records every added and removed combined span,
newly empty messages and withdrawn-rule watches for subsequent author review.
It does not silently equate more selected spans with better quality.

### Larger native replay and separate reference diagnostic

Android 026 and iPad 027 passed 15,365 cases with witness 012. Sentence scopes
prevent matches to an occurrence in a different sentence when both versions
have the same sentence count. Different sentence counts do not assert alignment.
The repeated-coffee positive retains both separate-sentence occurrences. New
revision 028 also withholds repeated eligible source words within one sentence
when occurrence ownership is unresolved, and protects contextual lecture
shorthand. Android 028 passed **26,365 cases in 978.113 seconds** with all accepted
baseline spans retained. Its delta from 026 removes ten spans, adds none, and
makes four previously nonempty cases empty. Author inspection confirms four
wrong meaning/occurrence removals and six plausible mappings lost to the more
conservative repeated-word guard; those losses remain a coverage cost.

iPad 028 was killed after 17,601 persisted cases, with no complete result.
Xcode reports “Test crashed with signal kill”; no current Jetsam report was
available through CoreDevice. Revision 029 added physical-footprint samples
and scoped temporary allocations; it was deliberately stopped after 21,601
persisted cases. Its first-case footprint was 2,868,792,008 bytes, rising to
3,360,001,696 bytes. It remains an incomplete diagnostic run, not a semantic
failure or another unexplained OS kill.

The QA file-hashing loop retained temporary Foundation read buffers across its
2.77 GB input scan. Revision 030 drains those buffers for each 64 KiB read and
bounds tokenizer temporaries during alignment. The physical iPad then passed
**all 26,365 cases in 521.856 seconds** (530.936-second xcodebuild operation).
First-case physical footprint fell to **71,516,928 bytes**; the maximum sampled
value over the complete run was **98,124,928 bytes**. This establishes bounded
memory for this QA workload, not a production memory limit, UI/audio acceptance,
or signed background-installation proof. Selection rules/data remain those of
028; iOS source changes after 028 bound temporary allocation lifetimes.

The diagnostic adds 100 underlying FLORES-200 dev sentences across every one of
the 110 directions, producing 11,000 correlated reference cases. They are
professional English-centered parallel references, not conversational turns or
word-alignment gold. The frozen hash-ranked sample excludes whole components
that touch any earlier corpus or devtest. The original 2022 archive, source
revision, CC-BY-SA-4.0 license and attribution are retained in
`vendor-research/conversation/flores200-evaluation-002/`. Initial acquisition
attempt 001 failed on an incorrect license path and remains recorded as failed.

The new exclusion index at
`artifacts/lexical-qualification-017/evaluation-exclusions.sqlite` contains every
acquired dev/devtest sentence hash. **Every future mining source must exclude
these identities.** This material is evaluation-only; the six inspected empty
English–Spanish diagnostic examples are now author-inspected diagnostic data,
not untouched acceptance data. No FLORES sentence entered witness mining.

Android 028 has at least one selected span in 4,439/11,000 reference cases
(**40.35%**), with combined p95 lookup **45.037 ms**. Swahili-source reference
availability is **39.8%** across ten targets; English–Swahili is **33%** and
Swahili–English **56%**. These are availability diagnostics, not accuracy,
independent conversational coverage, or proof of meaningful learning density.
The result demonstrates that additional full-sentence translation quality alone
does not close the selection/lexical coverage gap.

| Existing conversation replay | Android 028 availability | iPad 030 availability | Combined p95 ms, Android / iPad |
| --- | ---: | ---: | ---: |
| SMS, 3,600 | 842 (23.39%) | 858 (23.83%) | 40.567 / 21.783 |
| Multi3WOZ, 3,600 | 2,051 (56.97%) | 2,067 (57.42%) | 30.888 / 19.219 |
| XPersona, 2,700 | 1,045 (38.70%) | 1,060 (39.26%) | 25.581 / 15.787 |
| Explicit Swahili, 1,910 | 176 (9.21%) | 180 (9.42%) | 16.809 / 9.908 |

iPad 030 reference availability is 4,446/11,000 (**40.42%**), with combined
p95 **31.709 ms**. All 26,365 cases preserve accepted baseline spans on each
platform. The broad dictionary outputs differ between platforms in 90 cases;
combined outputs differ in 348. A complete pass is not exact cross-platform
output parity. The iPad delta from 027 is the same ten removals described above.
The separate qualification receipt is
`artifacts/bulk-native-qualification-028-030.json`; it binds complete reports,
source snapshots, data release, delivery measurements and explicit remaining
limits. `qa/immersion/qualify_bulk_language.py` reproduces those checks.

The Swahili replay consists of 191 underlying speech-derived turns crossed
with ten targets, including fragments, code-switching and unclear speech. Its
percentage must not be presented as general Swahili text-chat coverage. Source
licensing and native mechanics passes also do not establish meaning accuracy.

### Additional source acquired

The pinned [Amazon MASSIVE 1.1 distribution](https://github.com/alexa/massive)
contains **859,092 records across 52 locales** in the actual downloaded archive,
including Swahili. The archive is 40,251,390 bytes, SHA-256
`4cba5faa11c71437928e17cb1b9b3d8b8e727e7ea363a3a9a8045e19c0491577`.
The distribution's CC-BY-4.0 license, notices, repository commit and original
partitions are retained under `vendor-research/conversation/massive-1.1-001/`.
This is source acquisition only: it has not been mined or added to runtime
coverage. Localized slot entities cannot be treated as literal translations.
The publicly inspected README example's original ID 0 is excluded from any
future untouched evaluation in every locale. Further ingestion must preserve
partitions, slot provenance and prior-source duplicate exclusions.

## Noun forms and native qualification

Revision 007 contains eleven SQLite shards totaling **1,677,676,544 bytes**,
with **508,485 distinct lexical heads** and **4,017,866 indexed written forms**
(sum of per-language counts).
The release ID is
`c61654b1fe0006fcce7f79bcc90c0194e1bf918404015437b5cc693908c1ea6f`.
It adds 24,088 Arabic form records from explicitly supplied singular definite
forms and 160,083 Korean noun/particle records from nine finite morphology
rules. These are form records, not that many new meanings or translations.
Korean rules select particles by the noun's final Hangul syllable; the lexical
focus leaves the particle in the original language. Arabic offsets similarly
leave the definite article in place. Native readers require exact carrier
spelling and UTF-16 geometry. Existing competing analyses remain present.

The compiler records the carrier evidence and its dictionary/rule provenance.
The exact executed compiler for 007 is preserved under its `compiler-source/`
directory. A later count-label correction changed `supplied_carriers` to
`indexed_carriers`; it did not change SQLite payloads or the release identity.

Witness revision 003 is the previous 1,447,899-rule database rebound only after
checking that all old lexical evidence remains and no senses or translation
links changed. It is **300,105,728 bytes**, SHA-256
`e02f78f15d51320993c529147d139a0fddbb2a483315b0f21515b79701c7be91`.
Original context-mining provenance remains explicit. This is not new mining.

Native run 018 passed **15,353 cases** on Android (384.446s) and the physical iPad (233.368s xcodebuild operation).
All accepted baseline spans remained in the combined catalog result. One
earlier test incorrectly required the isolated broad dictionary to replace
"school" inside the protected phrase "at school". Run 016 explicitly checks
that the dictionary abstains and the accepted combined catalog supplies the
correct school mapping. The failed run 015 is retained.

| Reused conversation captures | Android combined availability | iPad |
| --- | ---: | ---: |
| SMS, 3,600 | 994 (27.61%) | 1,009 (28.03%) |
| Multi3WOZ, 3,600 | 2,106 (58.50%) | 2,122 (58.94%) |
| XPersona, 2,700 | 1,104 (40.89%) | 1,118 (41.41%) |
| Explicit Swahili, 1,910 | 171 (8.95%) | 175 (9.16%) |

These numbers measure whether a message has any selected vocabulary. They are
not meaning accuracy, token coverage, majority-chat acceptance, or production
installation results. Combined output has 125 platform differences; the broad
path has 38. The new noun forms do not improve Swahili source coverage in this
replay. The earlier run 016 gained 229 previously empty Android conversation
messages relative to run 014 and lost five where Korean noun-particle analyses
compete with an existing adverb. Run 018 also withholds additional ambiguous
outputs; its lower availability is shown above. Existing accepted primary catalog spans are still retained.

Author inspection of the earlier run 015/016 outputs found 13 additional semantic regression cases: twelve
literal substitutions inside an Arabic bus-station name and one French
"establishment" mapped to the act of founding in a hotel request. They are
recorded in `qa/immersion/noun_carrier_semantic_findings.json`; passing run 016's
mechanics does not accept these mappings. The Arabic name is confirmed by the
[Ajman public-transport station dataset](https://data.ajman.ae/explore/dataset/public-transport-stations/?flg=ar).
The distinct French senses are documented by the
[Académie française](https://www.dictionnaire-academie.fr/article/A9E2776).
The new selector adds conservative local place-name scopes and requires context
evidence when a coarse native gloss links multiple senses of one English
headword. Run 017 initially also withheld ordinary Arabic "cup" positives.
Snapshot 018 permits a direct English counterpart only when it preserves the
complete linked sense family; narrower counterparts still need context. Both
platforms now pass all 13 new negatives and the retained positives in fixture
011. This remains author-guided regression coverage, not independent accuracy.

## Larger corpus ingestion

`fetch_parallel_global_voices.py` pins all 55 unordered pairs of the eleven
languages, including all ten Swahili pairs. The archives occupy **417,457,947
bytes**, with **1,679,917,800 bytes** of archive members. The English–Swahili
archive contains 32,754 automatically aligned units. These are additional
source evidence, not already accepted mappings. Import 001 retains 2,948,161
distinct segments and 3,306,868 direct links: 2,337,774 development segments,
414,032 reserved and 196,355 excluded for overlap with existing sources.
Swahili contributes 29,217 development and 5,085 reserved segments. The imported
database is 2,141,052,928 bytes, SHA-256
`3334e3dd75483f52c6359c838ddf174ff1889340b4ac39db7efd03c174d54a7e`.
The distribution, original
notices, citation, archive hashes and unit identifiers are retained.

`build_corpus_exclusions.py` has hashed **5,856,064** distinct existing sentence
identities across every existing development and reserved partition, including
the raw Swahili export. Its 242,262,016-byte hash index contains no sentence
text. It prevents repeated source material from inflating support counts and
keeps earlier evaluation material out of the new mining input.

`import_parallel_global_voices.py` reads the direct TMX links, collapses
normalized duplicates, excludes entire connected components touching those
existing identities, and splits the remaining components into development and
reserved material. Negative deterministic IDs avoid collisions with the
earlier Tatoeba IDs. It retains all archive/unit attribution and source alignment
scores, without treating those scores as calibrated accuracy. No translation
links are inferred through a third language. TMX lacks article IDs, so the
split cannot establish document-independent evaluation.

The context miner now accepts PGV provenance explicitly rather than labeling it
as Tatoeba. Only development endpoints enter its lexical index, FTS table or
alignments. Schema 3 also supports the exact vocabulary focus inside indexed
carriers; it never assigns a complete inflected word the meaning of its stem.
The resulting witness compiler preserves source attribution and marks automatic
sentence alignment. Source agreement remains experimental evidence.

Build outputs are immutable revisions. Further corpus additions must exclude
all prior development and reserved identities before mining, preserve direct
source provenance, and get new native and semantic evaluations. Never merge
only successful witness rows: conflicting observations must remain in the
agreement denominator. The cumulative compiler validates the prior-source
exclusion hashes and dictionary-release adapter before rebuilding both corpora
together. Its test proves that contradictory new evidence withdraws an old
witness, while agreeing evidence can establish one. Complete-pair replacement
then updates only the requested directions, including deletion when a rebuilt
pair has zero acceptable rules; other pairs remain unchanged. The pair replacement
test passes. These mechanisms support staged expansion without success-only
unions or double-counted old evidence.

## Delivery boundary

The app-signed bundled installer and normal conversation integration are now
implemented as described below. Broader meaning/transliteration assessment,
representative conversational coverage, physical interaction and acoustic
speech acceptance remain open. No release-ready flag, store status or
subscription configuration changed in this expansion.

## Bundled native conversation integration — 2026-10-27

Development builds now call the broad dictionary reader from the normal
conversation path on both platforms, after local whole-message translation.
The starter catalog remains first in alignment priority. Source message text,
encrypted storage and relay payloads are unchanged.

The bundled-lexical-001 artifact contains 11 dictionaries and 55 bidirectional
context subsets: 347,264,592 compressed bytes, 1,865,830,400 expanded bytes if
every language were installed. Native clients prepare only the selected pair
from app-signed assets, verify expanded size and SHA-256, and atomically
activate complete SQLite files. Public caches contain no conversation text.
The data remains experimental linguistic evidence; no store-ready or semantic
accuracy claim is made by its manifest.

The preceding dictionary release 009 restores 8,530 entries with ordinary
lexical senses that were incorrectly disabled by an additional alternative or
form-of sense. Source eligibility and all prior sense/term links are retained.
This correction is reproducible with update_lexical_eligibility.py; source and
per-entry delta receipts remain in the artifact directory.

A 334-case development replay through the actual bundled reader completed on
the dedicated Android emulator and physical iPad. This is a small targeted
cohort plus retained failure cases, **not** a representative coverage estimate.
Android produced 151 combined spans versus 76 starter spans; iPad produced 152.
The known retained failures did not recur and starter spans remained present.
Median/p95 combined lookup time excluding translation was about 17/61 ms on
Android and 12/69 ms on iPad. Android first-time selected-pair preparation took
up to 6.5 seconds. Native runtime checks and these mechanical checks do not
independently establish translation or substitution accuracy.

Evidence: bundled-conversations-android-001/002.json,
bundled-conversations-ipad-001.json, bundled-lexical-android-test-001.log,
and the Mac's ipad-bundled-lexical-002 and ipad-bundled-conversations-001
logs/xcresults. The iPad check exposed and repaired a URL-identity cleanup bug
that had removed newly installed public cache files.

An in-progress Chinese rebuild corrects two structural exclusions: exact
supplied simplified/traditional forms marked unusable, and lexical words
classified as "character" by the upstream dictionary. Character links require
an existing published bilingual translation corroborated by a native gloss.
Their source senses remain contextual; no generic script conversion or
invented reading is introduced. Affected pair contexts must be recomputed
before this data replaces the current bundle.
