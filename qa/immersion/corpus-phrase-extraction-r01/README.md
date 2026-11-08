# Complete bilingual phrase extraction experiment

This frozen research protocol tests a missing comparison: a corpus-derived phrase
inventory retaining unaligned target-boundary variants, against mutual single-word
links. The original historical pilot generated one-to-one words. A later
`evaluate_statistical_units.py` follow-up did compare complete supplied dictionary
units: shared sense/POS/number, a mutual anchor, closed union edges and larger-unit
masking. It proposed 19 spans in 94 conversational diagnostics and was withheld
after contextual-role/sense errors. The new experiment expands beyond those
dictionary-supplied units; it is not the first multiword experiment. Neither
alignment consistency nor corpus frequency approves a translation for runtime use.

`protocol.json` fixes source selection, caps, provenance, tokenization, review and
resource limits before outputs. `prepare_inputs.py` freezes source-frequency keys
from the existing 9,535-message TRAIN diagnostic and exact evaluated-message
exclusions. `extract_pgv.py metadata` selects archive/unit identities without
reading target text; `fetch` then restores only selected endpoints through indexed
reads. `export` fills the bounded training sets in the original frozen hash order.
Failed or incomplete stages retain receipts. Fetch checkpoints are resumable;
completed freezes and exports must not be overwritten.

The first source is the retained Parallel Global Voices development partition,
starting EN–SW and EN–ES. It is automatically aligned published news, not friend
chat. A later conversational-corpus arm needs its own freeze. Records preserve
direct pair identity, original complete text and token/character spans, archive
hash/unit, component and license. The format supports reversing direction; it
does not establish the required ten-language/all-pair quality.

Private corpus and working outputs remain outside this source checkpoint.
`input-freeze-manifest.json` and `toolchain-manifest.json` bind exact inputs and the
Apache-2.0 fast_align revision. The PGV alignment distribution uses CC-BY-4.0;
dictionary corroboration uses separate CC-BY-SA-4.0 provenance. Publication review
and semantic acceptance are separate from this extraction experiment.

No production pack or native matcher is changed or enabled here.

After the complete training receipt exists, `train_alignments.py` freezes exact
commands, then runs forward/reverse five-iteration fast_align and both intersection
and grow-diag-final-and symmetrization. `extract_phrases.py` emits every consistent
boundary variant for the already frozen source keys. Original observations retain
pair IDs and exact source/target offsets; aggregate counts use distinct corpus
components. The diagnostic lexical tie score and missing-parameter floor are
explicit in each execution freeze. All competing target variants survive.

`python3 -m unittest discover -s qa/immersion/corpus-phrase-extraction-r01`
checks extraction geometry and score orientation with authored structural cases.
It does not certify bilingual meanings. In particular, recovering a multiword
target next to a shorter one is only a proposal for later contextual review.
