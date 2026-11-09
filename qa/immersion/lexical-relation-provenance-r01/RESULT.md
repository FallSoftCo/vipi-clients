# Retained lexical relation provenance — read-only result

The missing seasonal `fall→otoño` relation is a compiler identity-resolution omission, separate from the explicit-link policy. No compiler, dictionary, selector or app changed.

Private evidence: `/home/ai/Development/investigations/vipi-lexical-relation-provenance-20261109-r01/{cohort-freeze.json,route-schema-r01.json,trace-r01/,packed-trace-r01/}`. The keyed raw read retained 113 entries with individual canonical row hashes: 99.82 seconds, 26,550,272 bytes VmHWM, 327,350 bytes output. Its evidence SHA256 is `b4561383adff91b0b899b4c613eda0c79bd5d616fe20080d1cf85467fb99fe82`. Packed cross-check evidence SHA256 is `805caa783eae2722e69ebadd471040df8280fd779084f8451b0c2c5195b645ff` (32,557 bytes). Exact SQL is in the hash-bound scripts.

The established read-only Storage Box inventory is 4,428,693,504 bytes, with historical expected SHA256 `8c97e9de2ce8e94ce9754475a85eb27cd956ee0ba69491fe270376e3177ceb17`. Route, size, embedded upstream/compiler metadata and previous archive binding were checked; **no fresh whole-file hash** was computed. Current compiler reconstruction and packed observations are distinguished; this is not a reproduced historical build.

## Exact diagnostic chain

- Spanish native entry 161656 (`otoño`) publishes one gloss, `autumn, fall`, with masculine tag. The existing bare-gloss parser accepts both English words.
- English `autumn` resolves uniquely to entry 3288. Both packed endpoints contain eligible `native-gloss:es:161656`, marked `explicit=0`; both also contain the explicit season translation group. Nonexplicit direct-English relation evidence already exists here. Its flag intentionally prevents an unreviewed foreign-to-foreign pivot.
- English `fall` has two accepted noun entries, 15812 and 15814. The resolver returns no entry because it demands exactly one. The native seasonal meaning occurs at 15812, sense index 2. Entry **15814 describes whale hunting**, not autumn; it has no packed terms. This corrects the earlier possible association of that zero-term entry with the season.
- Packed 15812 contains three explicit translation groups (gravity, status loss, decline), with no seasonal/direct-otoño link. Dropping the explicit requirement cannot restore a relation that was never emitted.

## Broader frozen cohort

All noun forms from all 29 audit additions were retained: 110 form records / 95 lexemes, including incomplete forms and capitalized entries. Seventeen forms have zero terms; 108 have complete supported geometry; 43 have eligible nonexplicit native-gloss terms. These are overlapping form strata, not recoverable vocabulary counts.

The trace includes 50 Spanish entries (the cohort plus the diagnostic otoño entry). Fifteen pass the bare-gloss parser, yielding 17 English resolver requests: 14 unique, two ambiguous-entry, one without a leaf/nonalias entry. Parser failures include multiple distinct gloss leaves, semantic/register tags, published form/alias relations, and descriptive gloss grammar. They must remain distinct from restrictions on existing packed terms. English self-resolution is a lowercased diagnostic lookup, not proof of a relation for uppercase source entries.

Every one of the 17 zero-term forms is retained with its trace in `packed-trace-r01/evidence.json`. They include forms of names/abbreviations, inflections/aliases, homographs and ordinary nouns. Their absence is not uniformly a defect: English entries are not source inputs to the foreign bare-gloss parser, so an English parser rejection alone does not explain every missing translation group. Sixteen published form/alias edges and their exact same-POS target entries were retained without collapsing identity or asserting synonymy. Alias traversal needs relation-specific semantics, qualifiers and cycle/ambiguity handling; blanket alias inheritance is unsupported.

## Concrete next implementation proposal (not executed)

Add a separate research relation representation for accepted foreign bare-gloss evidence: target native entry and sense index, exact published English spelling/POS, all matching English entry candidates, qualifiers, gloss/source hashes, and relation kind `direct_english_gloss_candidate`. Preserve ambiguous resolution instead of dropping the relation; do not fabricate an English sense ID, attach the edge to every homograph, or allow a foreign-language pivot. Keep current packed terms unchanged as a control. This generic rule is supported by the explicit otoño gloss, and should be evaluated over the entire frozen cohort rather than whitelisting fall.

Existing eligible nonexplicit direct-English links form a separate evidence stratum. Published form/alias links remain separate and unresolved until their qualifiers and relation types support a bounded policy. None of these records alone authorizes emission. Actual source and target occurrence roles are required to distinguish examples such as verbal `order` with `pedido`; sentence context must then distinguish seasonal fall from descent. A dictionary edge and a parallel pair are candidate evidence, not gold labels. Name/title protection remains a separate problem.

The next smallest decisive experiment is relation serialization/parity on this frozen cohort plus supplied-token bilingual role qualification as described in `OCCURRENCE_ROLE_PLAN.md`, before any ranking or projection. No broad all-senses agreement gate, per-word patch, training or activation is proposed.
