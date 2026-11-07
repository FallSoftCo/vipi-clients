# Source-only lookup experiment

This is a bounded experiment, not an installed pack or an approved source-only
scope expansion. The apps retain their current native readers. Existing frame
assessments normally require a source and target context; copying their records
does not remove that requirement.

The candidate reuses exact current record identities for explicit request
constructions, complete compounds, a small vocabulary list, noun contexts and
social clauses. It leaves unknown source characters unchanged. Swahili finite
prefix choices are concatenated before tokenization. Different target meanings
for the same source interval abstain. Explicit lowercase target records avoid
mistaking the retained capitalization matrix for different meanings.

Run with installed Python only:

```sh
python3 qa/immersion/source_lookup_experiment/build_candidate.py --data data/immersion --output /disk/new-candidate
python3 qa/immersion/source_lookup_experiment/run.py --candidate /disk/new-candidate --protocol qa/immersion/source_lookup_experiment/native-pilot-protocol.json --output /disk/new-report.json
```

The builder refuses an existing directory; the runner checks the frozen pack
and matcher hashes and refuses an existing output. No network, provider calls,
or app writes occur. Native source tokenization must replace experimental Python
token counts before integrating a presentation.

## Measured result

The retained experiment froze before acquiring 200 public UCI nonspam messages,
hash ranks 400–599. Candidate3 contains 571 scopes from 519 exact retained records
and occupies 467,223 JSON bytes. These are only 57–63 distinct focus strings per
pair (59 in each English direction); record count is not vocabulary coverage. It selected 20 spans in 18 English→Spanish
messages and 18 spans in 16 English→Swahili messages: 9% and 8% availability.
Mean message depth was only 0.74% and 0.68%. The earlier 120-rule candidate
covered 5/200 in both directions on the same sample. Exact whole-message
references covered none; this is not a comparison against the complete native
translation/alignment path.

All 38 selected spans were inspected by the same authoring agent. No clear
material meaning error was observed; one `No`→`no` span is ineffective and
sentence-initial casing is imperfect. This is not independent bilingual
acceptance. Twenty-four of 25 bounded controls passed. The failed gratitude
control is a missing `Thank you` mapping, not an incorrect replacement. None
of these figures meet the requested product standard. Reverse directions have
only authored control evidence; no non-Roman direction is qualified here.

The first broader run exposed capitalization collisions and an incorrect
token boundary between Swahili prefixes. Its failed output remains in the
investigation receipts. The final 200 messages were not used to repair that
run; prior project overlap with UCI has not been measured. All inspected rows
are now diagnostics, not future untouched acceptance data.

Retained outputs, original sampling pins, mixed sentences and per-span review:
`investigations/vipi-immersion-reconciliation-20261107-r01/candidate3/` in the
parent Development directory. UCI attribution: Almeida, T. and Hidalgo, J.,
*SMS Spam Collection*, DOI 10.24432/C5CC84. The
[UCI dataset card](https://archive.ics.uci.edu/dataset/228/sms+spam+collection)
declares CC BY 4.0. Public QA texts must not be confused with private chats.

## Native interface proposal

Each accepted match needs source start/end UTF-16 offsets, exact `original`,
`targetText`, optional `reading`, mapping ID and record SHA-256, pack/catalog
SHA-256, matched source-context start/end, and `kind: phrase|sentence`.
Each unit's target offsets index its own target text, starting at zero. Native
source token cost comes from the same whole-message tokenization as the density
denominator. Partial units do not manufacture a full translation. Sentence join
spacing must apply only to sentence units, not phrase substitutions. Non-Roman
targets require a meaning-bound reading before becoming visible.

The proposed interface is data, not a new shared runtime. Native owners must
validate geometry, context/pack identity, protected ranges, overlap, reading,
and cancellation before adoption. `controls.json` retains actual experimental
outcomes including the known miss rather than masking it with a passing suite.

## Combined native measurement

`../MacLiveImmersionProbe.swift` executes the current source-reference path,
then at most one installed Apple full-context translation on a miss and the
actual bundled lexical/frame readers. It saves all mixed outputs and reading
spans at density 0.25 and 1, native token ranges and diagnostic rejection counts.
It is a separate measurement from this candidate. The fixed pilot protocol
contains the first 20 source messages from the frozen sample, repeated into
Spanish, Japanese and Swahili without outcome-based selection. Unsupported
translation or absent payloads remain explicit failures; there is no fabricated
fallback. Mac execution does not qualify iOS/Android, offline behavior, listening
quality or independently correct translation.


The probe compiled and executed in the existing macOS 26.6.2 VM. Its 60-case
readiness run made zero translation calls: en–es and en–ja were supported but
not installed, while the Apple-only en–sw backend was unsupported. Production
Swahili uses ML Kit instead; this probe does not qualify or reject that path.

An explicit replay mode binds supplied provider text to the source capture SHA.
On 34 retained authored/contrast messages, 32 current native alignments executed;
French and German were incomplete because their staged lexical shards were
absent. Both densities had 17/32 messages with spans. Density 0.25 selected 18
spans with 10.75% mean source-token depth; density 1 selected 25 with 14.25%
depth. This is a reused diagnostic, not fresh provider execution or a population
coverage estimate. The known full-translation error `light bag` → `bolsa de luz`
remains in the evidence; its current inline span flips only `bag` correctly.

QA `mixed`/`visible` strings are literal replacement diagnostics, not a rendered
native bubble or the production copy/accessibility composer. In particular,
adjacent Japanese-source English spans print `togetherlunch` here; the native
copy composer already separates those words and visual slots have padding.
The resulting speech-boundary investigation identified a separate real audio
concatenation issue, owned by the Apple client workstream. No raw diagnostic
string should be treated as physical-device visual or listening acceptance.
