# Frozen corpus occurrence evidence — completed

Apertium morphology and contextual disambiguation completed on all **14,004 frozen endpoints / 131,705 tokens**. The evidence join completed for all **1,480 newly eligible source-name heads**, 12,485 observations and 12,500 head-observation joins. This is the existing diagnostic cohort, not the entire immersion catalog or representative translation accuracy.

Before counting any role-conditioned result, the join exactly reproduced every legacy explicit-link alternative identity and its independent source-occurrence, pair, component and paired-occurrence hashes. Existing dictionary terms, eligibility reasons, guards, masks, corpus alignments and selector behavior were not changed.

## Availability on the identical legacy pool

| Evidence retained | Heads | Target alternatives | Independent source-focus occurrences | Parallel pairs | Components |
|---|---:|---:|---:|---:|---:|
| Legacy explicit-link envelope evidence | 1,480 | 1,874 | 5,857 | 5,512 | 5,040 |
| Same evidence, both exact forms tagged NOUN | 1,335 | 1,683 | 5,090 | 4,848 | 4,431 |
| Difference | −145 | −191 | −767 | −664 | −609 |

These are independent availability denominators, not message counts, semantic judgments or additive categories. A removed observation can reflect a true POS mismatch, unknown/misaligned analysis or a tagger error. No claim is made that the losses improve meaning accuracy or retain every valid noun.

Within the legacy eligible pool, 12,450 distinct head-observation/form pairs reduce to 11,034 with noun roles on both sides. Source-side results include 646 ADJ and 87 VERB classifications, plus 340 unassessable form pairs; target-side results include 396 ADJ and 59 VERB classifications, plus 374 unassessable pairs. These overlap across sides and are not independent source-message counts. Full patterns remain in the private post-audit receipt.

## Exact form scopes and separate relation strata

The join examines complete dictionary form scopes at their **absolute original UTF16 coordinates**, with endpoint identity and exact text verification. It does not require every token in an alignment envelope to be a noun. This preserves evidence for nouns whose envelope also contains an article or adjective, without moving a repeated word's evidence to another occurrence.

There are 1,317 eligible explicit head-observation/form pairs whose target noun form is smaller than the aligned envelope; 1,103 have noun roles on both exact forms. **All 1,317 retain a union-crossing reason** at the smaller focus. Larger source/target unit masks and missing mutual anchors also remain recorded. This is additional form-level evidence, not permission to ignore those guards or emit the smaller head. Across all exact-form evidence, eligibility plus noun roles reaches 1,337 heads / 1,706 alternatives; requiring the recorded alignment and full-sentence masks to be clear yields 1,334 / 1,674. These are separate availability axes, not a new selected output.

The relation database preserves three distinct strata:

- **Old explicit shared links:** 33,716 retained relation rows. All original source/target term-reason guards remain enforced in legacy eligibility accounting.
- **Old nonexplicit shared links:** 2,608 rows across 259 heads, 1,222 independent source-focus occurrences/pairs and 1,102 components. Their original `sense_not_explicit` reasons remain; they were not promoted into the explicit eligible pool. Raw roles remain available separately.
- **New direct-English unresolved candidates:** 785 rows. Twelve of the previously frozen 17 candidate relations find occurrence evidence, spanning 73 heads, 495 independent source focuses/pairs and 460 components. Both-form noun evidence remains for 64 heads, 455 source occurrences, 458 pairs and 425 components, with 74 alternatives. Source-entry/sense identity remains unresolved in every record.

For a new direct relation, the source role belongs only to its exact occurrence/unit span. Every candidate source form retains its own number agreement, role and guard reasons. No first source form is silently chosen, no shared sense is fabricated, and foreign-to-foreign pivoting remains unsupported. The original 17 serialized records are unchanged. Strata overlap in words, heads and occurrences; their counts must not be summed as unique coverage.

## Execution and immutable closure

Annotation ran once in **88.167 seconds**, with 111,132,672 bytes parent VmHWM and 13,813,008 bytes of retained raw streams plus SQLite offset/hash index. It reconstructed exactly the frozen 7,115 selected pair associations from the original 40k manifest, verified text/token geometry, rejected embedded NULs, used 438 fixed batches of at most 32 endpoints per language, and accepted only provably empty terminal flush records. No full JSON duplication of annotation streams was created.

The original join hit its 90 MiB SQLite page cap after 41.776 seconds. Its 94,363,648-byte partial database, code, protocol and failure receipt remain intact. Exact partial JSON payload was **55,811,439 bytes**, excluding identifiers/index overhead; an earlier 57.8 MB shorthand was inaccurate. The measured physical size justified the root-authorized resource-only r02 amendment. Annotation was not replayed, and all semantic, identity and eligibility logic remained byte-equivalent after reversing the declared resource/path/predecessor-binding changes.

The amended join completed in **146.954 seconds**, with 129,454,080 bytes VmHWM, 200,459,849 logical proof bytes and a **313,032,704-byte SQLite database** containing 198,943 immutable objects and 37,109 relation rows. This stayed within one CPU, 1 GiB address space, 300 seconds, 512 MiB join output and the unchanged 8 GiB free floor. The aggregate annotation-plus-join output is below the 544 MiB ceiling; the admitted reservation was 640 MiB.

A bounded read-only containment audit established that **all 58,978 objects in the failed prefix have identical kind/data bytes in the completed database, and all 10,489 prefix relation rows are present**. Nothing was deleted. Role streams, every alternative/reason and original corpus/dictionary provenance remain on production.

Production evidence root: `/srv/fallsoft/staging/vipi-apertium-corpus-evidence-20261109-r01`.
Private small receipts: `/home/ai/Development/investigations/vipi-apertium-corpus-evidence-20261109-r01`.

- Completed database SHA256: `03415f4547ed645a9dc5e9283ab4bfb77621e8ebb801f46f608a75b6053b01e3`.
- Summary SHA256: `29f77f986ddad1bfe8c4568e6679b7b6249759d9842e2115291ede9f68fb17be`.
- Join receipt SHA256: `e44ec6dc3691f4b047b8bf106333e9f6b7ba57fafd6ab65ba94d898a52e5f426`.
- Annotation/source closure and all small receipts are bound in `completion-receipt-r02.json`.

The result supports using actual bilingual occurrence roles alongside retained morphological alternatives and dictionary relation provenance in a later lexical-choice experiment. It does not resolve same-POS meaning, certify names or authorize a translation candidate. No training, ranking, selector projection, app change or catalog activation occurred.

## Final read-only loss and witness audit

The final audit took 3.871 seconds and 106,958,848 bytes VmHWM. Its summary and complete selected proofs occupy 216,401 bytes before receipts. All matching diagnostic relations were retained, with full parallel sentences, original owner/ID provenance and referenced dictionary/role evidence; no alternatives were truncated.

On the same legacy eligible envelope pool, role conditioning removes 1,416 form pairs and **145 heads / 767 independent source occurrences / 664 pairs / 609 components**. Applying existing exact-focus alignment/mask reasons *after* noun roles removes a further 1,093 form pairs and **1 head / 664 source occurrences / 599 pairs / 545 components**. These are ordered set differences, not sums of overlapping rejection flags. Of the latter form pairs, 901 have a larger source-unit mask and 339 a larger target-unit mask; these overlap. The separate smaller-envelope pool above remains alignment-blocked and is not folded into this legacy funnel.

| Non-noun or unassessable cause | Source form pairs | Target form pairs |
|---|---:|---:|
| VERB | 87 | 59 |
| PROPN | 0 | 0 |
| ADJ | 646 | 396 |
| Other mapped roles (ADV/DET/NUM) | 33 | 27 |
| Unknown analysis | 16 | 64 |
| Inside a larger analyzer unit | 205 | 193 |
| No mapped overlapping analyzer span | 119 | 113 |
| Unmapped tag | 0 | 4 |
| Total unassessable (last four rows) | 340 | 374 |

Rows can overlap across sides; they are not independent losses. Zero PROPN here describes only the already eligible legacy noun-link pool, not the whole annotation inventory or successful name protection. Multiword analysis is left unassessable at the smaller focus rather than assigned the containing phrase's role.

The private diagnostic proof file retains all three direct fall→otoño pairs (source/target sentence IDs **19431/520560**, **36491/505688**, **55047/1221621**). The first and third have NOUN/NOUN exact forms with no recorded envelope/focus reasons. The middle pair discusses why autumn is called “fall”: its source focus is unassessable, the target is NOUN, and noncontiguous alignment, focus outside target variant, missing mutual anchor and crossing reasons remain. The published direct gloss supplies candidate evidence; it does not choose between English entry 15812 and 15814 or establish a sense from noun tags. Entry 15814 is the whale-hunt entry, not the autumn sense. Both source-form alternatives, their original name guard and inherited conditional exception remain explicit.

Both order→pedido pairs retain the same eligible explicit noun link and clear recorded alignment/mask checks. **4053872/9816938** is nominal on both sides; **436505/436506** is verbal on both sides. The latter therefore cannot be counted as noun occurrence support merely because its spelling has a dictionary noun form. This is a concrete benefit of occurrence-role evidence, without proving other noun-tagged senses correct.

There is **no exact name→llamas relation row in this joined cohort**. The prior frozen diagnostic case 025 is retained separately with full contexts and hashes: English name is NOUN, Spanish llamas is VERB after Apertium disambiguation, while the raw Spanish morphology contains both noun and verb readings. It is not counted as a newly recovered corpus result.

The evidence now supports evaluating lexical-choice mechanisms on exact bilingual noun-form occurrences while keeping published direct-English candidates unresolved and separately identifiable. The remaining decision concerns same-POS target choice and genuinely independent context evidence; neither blanket guard relaxation nor an all-senses-agree gate follows from these counts. No further inference, ranking or projection was run. Both databases remain on production pending root review.
