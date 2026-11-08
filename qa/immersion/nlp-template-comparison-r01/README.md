# Bounded source-only NLP comparison

This experiment compares exact phrase windows, the existing finite `ContextMappingMatcher`,
and typed possessors plus attested source forms. It does not enable a language pack or change
the production matcher. The recognized context and the emitted source unit have different
ranges: recognizing `bring Alice's book` can authorize `book` without rewriting the name,
possessive, verb, tense or surrounding grammar.

`contract.json`, `schema.json`, `semantics.json`, `payload.json` and `authored-cases.json`
are frozen inputs. `freeze.json` binds them to the builder and exact retained sources.
There are ten families, 38 patterns, 38 target faces and 121 authored diagnostic cases.
`proofs.json` retains the source records and sense/form links. Existing frame assessments
are not presented as independent approval of new source-only contexts.

## Fair controls

The exact arm includes every already-indexed expansion of the six reused finite frames.
It also includes reusable short contexts such as `birthday party`, `phone charger` and
`bank account`. These already work inside longer sentences containing unfamiliar names.
A finite matcher is not credited with extra coverage merely for representing the same
enumeration differently. Typed and finite arms inherit the exact arm.

The generic word fallbacks are explicitly diagnostic controls. They intentionally expose
whether compound masks stop unsafe smaller matches. Their raw availability is not an
estimate of safe source-only immersion. Existing native whole/sentence-reference routing
is captured separately; a source catalog hit is not a simulated translation or alignment.

## Scope and ambiguity

All recognized atomic scopes survive missing target data, learned concepts and density
limits. An overlapping output must have the permitted output ID and exact scope for every
overlapping mask. Longer contexts do not erase shorter masks. Conflicting meanings with
overlapping focus are withheld rather than resolved by arbitrary priority.

Bare `hot dog` is recognition-only: it has a permitted complete output scope but an empty
face map. A longer food context may supply that face; bare compound-shaped text does not
establish food sense. There is no invented Swahili hot-dog translation. `raise the bar`
retains an ambiguity mask with no approved output. `high school` and `country music`
permit explicitly scoped head output, not generic substitutions of their modifiers.

`structural-overlap-controls.json` contains three synthetic recognition overlays for
testing mask/conflict handling. They are not linguistic patterns and are excluded from
TRAIN reach. The 121 authored cases and all uncensored native captures remain unchanged.

## Morphology and costs

Written forms such as `brought`, `reads` and `books` are bound to retained source entries.
Multiple analyses remain separate. Using a complete attested form as context does not
authorize emitting the legacy root-only range from that form. This experiment does not
generate target agreement or inflect arbitrary targets.

The separate pinned HFST/lexd feasibility capsule is in
`../hfst-morphology-feasibility-r01`. That actual desktop analyzer/generator experiment
has documented Swahili gaps and wrong analyses; it is not installed in either client and
is not silently counted as a fourth successful arm here.

All arms use actual platform token ranges, the same 10/25/50% native-word budgets,
whole-token output rules, protected spans and immutable known-concept snapshots.
Native source-window limits remain eight words, 256 UTF-16 units per window and 4,096
windows per message. Numbers and URL ends that are not native word-window endpoints
remain observable matching misses. No window expansion is hidden in this comparison.

## Reproduction and evidence

`prepare_payload.py` builds the frozen payload from the exact retained frame/lexical
sources recorded in `freeze.json`. `preflight-r00` preserves a pre-execution builder
correction: a language-key mismatch initially omitted six intended diagnostic component
faces. No comparator outputs were used for that correction.

`reference_compare.py --geometry <native rows.jsonl> --output-dir <new directory>` runs
an independent Python projection using the platform's actual UTF-16 geometry. It reports
recognized-context reach separately from generic-control availability, with no provider
calls. Its timing is not native runtime timing. It refuses to overwrite its prior output.

The frozen TRAIN source contains all 9,535 selected speaker-0 turns from retained
BlendedSkillTalk TRAIN ConvAI2 role-play conversations. The original CC-BY-4.0 provenance
and source hash are in `train-source-protocol.json`. This is reused diagnostic material,
not an unseen worldwide-chat distribution. The 121 authored cases are contrast tests,
not a conversation coverage sample. No evaluated text becomes a new accepted pack row.

Private controller evidence is retained under
`investigations/vipi-immersion-reconciliation-20261107-r01/nlp-template-comparison-r01/`.
Both native owners retain their original captures, source closures, timing and memory
receipts in their respective Apple/Android investigation directories. The fixed independent
review packet binds actual captures and records preceding TRAIN context. Semantic review,
native parity and production activation are separate decisions.

The current app's nullable partial-result seam cannot carry an atomic mask into its
existing translation/alignment fallback. Proving mask retention within these source-only
arms does not establish all-path product protection. Production integration requires a
nonnullable recognition result or an equivalent explicit abstention contract.
