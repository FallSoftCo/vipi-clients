# Apertium lexical selection: offline component assessment

Read-only assessment, 2026-11-08. No package installation, source checkout,
training, new corpus processing or probe execution.

**Recommendation:** use Apertium's established corpus-trained lexical rule learner
as the first offline comparison for compatible noun/verb/adjective alternatives,
after qualifying occurrence labels and token identities. It can avoid inventing a
classifier. It does not remove the need to establish correct labels, supply missing
translations, preserve phrase boundaries or abstain when context is insufficient.
The extracted installation is not yet a complete training toolchain.

## What is already present

Private root:
`/home/ai/Development/investigations/vipi-production-delivery-20261107/apertium-transfer-feasibility-r01/root`.
The retained protocol pins `apertium-lex-tools` / library `0.4.2-2build3`,
Apertium `3.9.4-1build1`, and EN–ES `0.8.1-2`. Existing acquisition receipt verifies
lex-tools package SHA-256
`1085042a8d27c7addacbb9353e2caf13b746ff9d9d3273dd138486784f078b5c`.

| Private executable | SHA-256 |
| --- | --- |
| lrx-proc | ac46dc1b0a92a9f8eb9a77ef3f152839b0561bba4a7a4dfa57cb771a877d9cf9 |
| multitrans | 1d2f3692d9500f197516120893cd38eef0390c69966d5326e53210784ce6a93f |
| process-tagger-output | a953aca079b7fc13b28a548e4dac60b83cc129385716cb85128f9b92311b3f85 |
| yasmet | 5deb3ff4d2f3c7f792456da5a7bfb611fefbce3b6f1107e1ea81bdcfdfba31b4 |

`lrx-comp`, Python training scripts and the newer training wrapper are absent
from this extracted root. EN–ES already includes compiled `eng-spa.autolex.bin`;
its mode runs `lrx-proc -m` after bilingual lookup and before structural transfer.
Thus the prior failed full-translation diagnostics already passed through the
pair's existing lexical selector. Merely inserting that same selector again is
not a proposed improvement. Binary presence is not a newly executed qualification.

## Established learning procedure

The supported module selects among bilingual alternatives after source
morphological disambiguation and bilingual lookup. It targets translation choice
within a POS, rather than resolving every fine-grained dictionary sense. Rule
matching can use lemmas/tags and surrounding units; candidate choices must exist
in the bilingual stream. [Official lexical-selection overview](https://wiki.apertium.org/wiki/Lexical_selection),
[rule module](https://wiki.apertium.org/wiki/Apertium-lex-tools).

The official parallel workflow analyzes both corpus sides, aligns tokens,
constructs bilingual alternatives, extracts aligned candidate occurrences, builds
a frequency default, and learns context-dependent overrides. It documents both
maximum-likelihood counts and maximum-entropy weighted features/YASMET. This is
an existing classical approach, not a requirement for a new neural model.
[Official training documentation](https://wiki.apertium.org/wiki/Learning_rules_from_parallel_and_non-parallel_corpora).

Version-matched source gives the concrete feature contract: `MAX_NGRAMS=2` with
`range(1, MAX_NGRAMS)` extracts previous+current, current+next, and
previous+current+next tagged-lemma patterns. Targets come from aligned target
occurrences; counts are compared with a global frequency default. These are local
lexical contexts, not dependencies, dialogue history or native semantic senses.
[0.4.2 ngram-count-patterns.py, lines 19–20, 64–105, 124–171](https://raw.githubusercontent.com/apertium/apertium-lex-tools/v0.4.2/scripts/ngram-count-patterns.py).

The frequency extractor considers lexically ambiguous bilingual units, counts
aligned tagged target units and rejects a first-tag mismatch when emitting its
lexicon. It does not prove that either analysis or alignment is correct. Its
counting code should not be described as independently validating every target
against a semantically approved candidate set.
[0.4.2 extract-freq-lexicon.py, lines 47–76 and 99–118](https://raw.githubusercontent.com/apertium/apertium-lex-tools/v0.4.2/scripts/extract-freq-lexicon.py).

The stock XML rule emitter permits noun, lexical verb and adjective targets;
**adverbs are excluded**, so degree/additive `too` is outside that unchanged
learner. It also rejects selected punctuation/unknown-word patterns and emits
lemma/tag matches and weighted target selections. An adverb extension would be a
separate explicit implementation change, not a capability already demonstrated.
[0.4.2 ngrams-to-rules.py, lines 12–13, 40–71 and 76–113](https://raw.githubusercontent.com/apertium/apertium-lex-tools/v0.4.2/scripts/ngrams-to-rules.py).

A newer official wrapper orchestrates analysis, fast_align, candidate extraction,
frequency counts and XML generation. Its inspected parallel path uses count-based
rules; the maximum-entropy branch there is commented out. The separate documented
ME scripts remain an option. The wrapper also rewrites corpus characters and
realigns tagged streams, so running it unchanged would neither preserve our raw
text/token contract nor reuse our existing alignments automatically.
[Official wrapper source, lines 118–233 and 235 onward](https://raw.githubusercontent.com/apertium/apertium-lexical-training/master/lexical_selection_training.py),
[project requirements](https://github.com/apertium/apertium-lexical-training).

## Label validity is a separate problem

Our retained `visit → visitas` example is specifically a **false occurrence POS
inferred from a dictionary link**: the surviving noun identity matches the
spellings, but the actual pair says “sites you visit” / “sitios visitas”. We have
not shown that Apertium tagged that example as a noun; no such probe was run.
The corpus inventory also found `visitar` with a dictionary “meet someone” label
in an example about visiting sites. These are failures of promoting dictionary
identity into contextual annotation, before any learner is involved.

A trained selector has a different failure mode: even with a formally unique
training label, wrong source/target analyses, bad alignment or an incorrectly
assigned target identity can make the learner confidently reproduce that error.
Repeated support is not correction. Conversely, several fine-grained source
senses can legitimately share one target realization; lexical selection need not
manufacture different labels for them. Both distinctions must survive evaluation.

## Practical next step, proposed only

Use the existing Spanish `play` musical/game alternatives as a candidate audit
for compatibility with this established learner. `visit` noun/verb is primarily
an upstream analysis test, while `too` requires a separately scoped adverb
extension. Swahili musical `play` is absent from the complete-backed pool; no
selector can choose a missing candidate. Names and protected spans remain outside
ordinary lexical acceptance.

Before any training job, freeze a small occurrence manifest with exact source and
target spans, retained alignment links, real occurrence POS/lemma evidence,
complete candidate identities and explicit unresolved labels. Reconcile Apertium
lexical-unit indices with our original UTF16/native tokens; retained raw
fast_align indices cannot simply index a differently tokenized analysis stream.
Record missing candidates and disagreements rather than assigning the sole
surviving dictionary sense as the label. Native coarse POS evidence is useful
here, but cannot resolve same-POS meanings or repair target-side analysis.

Then qualify the version-pinned upstream scripts/compiler in a separately bounded
plan, using existing alignments only where the index mapping is demonstrated.
Compare frequency-only selection with learned local rules on identical held-out
occurrences, retaining every abstention and whole-output defect. Our product's
abstention and protection requirements need an explicit adapter: ordinary
Apertium translation defaults are not permission to emit uncertain vocabulary.
No adapter, training job or runtime integration is implemented by this assessment.
