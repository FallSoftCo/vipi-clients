# Complete bilingual phrase extraction experiment

This frozen research protocol tests a missing comparison: full alignment-consistent
phrases, retaining unaligned target-boundary variants, against mutual single-word
links. The historical pilot only generated one-to-one words. Neither alignment
consistency nor corpus frequency approves a translation for runtime use.

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
