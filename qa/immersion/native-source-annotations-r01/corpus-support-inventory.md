# Retained corpus support inventory — 2026-11-08

The complete dictionary-backed pool contains alternatives worth testing for
source-context selection, particularly in Spanish. It is not merely one default
face per source word. However, candidate existence is uneven across languages,
and a shared sense ID is not occurrence-level sense annotation. Selection alone
cannot recover a missing candidate or turn dictionary incompleteness into truth.

The single bounded read-only execution of `corpus-support-inventory.py` inspected
`variants`, `components`, `ranked`, `units` and `corroboration` schemas, then read
the retained observation streams and paired examples. It neither re-extracted
phrases nor downloaded, trained or changed a target. All 13,630 shared-complete
variants survive this inventory, grouped into 7,606 pair/arm/source-key groups.
Hashes and counts are in [the receipt](corpus-support-inventory-receipt.json).
The detailed [private inventory](/home/ai/Development/investigations/vipi-corpus-support-inventory-20261108-r01/inventory.json)
is 14,299,010 bytes, SHA-256
`c52ac3eb3256803c44d38f41acb1dd318d227bae26dc33a21331201db02f735c`.
It resides outside the nearly full original experiment allocation.

## Pool and identity distinctions

The table shows grow-diag-final-and, the complete_grow arm's pool. The receipt
also gives the entire intersect and mutual-word inventory. Arms overlap and must
not be summed as independent data.

| Measure | EN–ES words | EN–ES phrases | EN–SW words |
| --- | ---: | ---: | ---: |
| Source keys | 1,848 | 7 | 663 |
| Candidate variants | 3,774 | 9 | 815 |
| Source keys with multiple explicit dictionary meanings within a POS | 1,570 | 0 | 581 |
| Source keys retaining multiple supported explicit meanings within a POS | 994 | 0 | 246 |
| Exactly one supported explicit POS/sense identity in total | 706 | 5 | 359 |
| No supported explicit same-POS identity | 87 | 2 | 43 |
| Multiple target spellings | 983 | 1 | 132 |
| Multiple supported target POS/sense/lexeme identities | 1,159 | 1 | 282 |
| Distinct aligned source spans within paired records, summed by key | 82,863 | 161 | 16,056 |
| Source keys with only one connected component | 149 | 0 | 79 |

There are no Swahili multiword source keys in this shared-complete pool; multiword
targets of a single source word are still possible. Intersect adds only nine
Spanish phrase keys (11 variants). Thus the wider raw phrase pool should not be
confused with a rich, dictionary-supported multiword inventory.

“Supported explicit meaning” here requires an eligible explicit source dictionary
sense shared with an eligible target term of the same POS. Generated native-gloss
IDs remain in the detailed confusable records but do not count as explicit source
meanings. These identities are not guaranteed exhaustive, independent or correctly
assigned to the corpus occurrence. Different spellings can denote one lexeme;
different lexeme/sense identities can still express the same meaning. Multiple
same-POS, singleton-total and zero columns are not exhaustive partitions: a key
can have one sense under each of multiple POS categories.

The observation count deduplicates alternative target boundaries for each
pair-record/source-span/arm/key. Different records can still duplicate source
text; overlapping source keys count separately. Connected-component counts are
also retained per key, but neither measure establishes statistical independence.
The existing data cannot supply a certified count of independent sense-labelled
source examples. A singleton surviving link is not proof of an unambiguous word.

## Fixed 116 probes and confusables

Casefolded boundary spelling lookup finds at least one complete_grow source key
in 116/116 Spanish probe texts and 114/116 Swahili texts (872 and 385 key matches,
respectively). This is candidate availability, not native matcher geometry,
correct contextual coverage or whole-message acceptance. Duplicated probes remain
as frozen. The private artifact records all matches and exact input hashes.

Retained grow candidates, with raw aligned-observation counts:

- Spanish `play`: `tocar` (3), `jugar` (12), `juego` (6), `jugada` (1). The `tocar`
  link has explicit musical-instrument senses, and its retained bilingual example
  describes teaching people to play the cajón. Thus case 074 has an existing
  musical candidate to test. Swahili has only `mchezo` (3), a noun; the corresponding
  musical verb candidate is absent from this complete-backed pool.
- `too`: Spanish `demasiado` (42), `muy` (30), `también` (89); Swahili `sana` (16),
  `pia` (29). Explicit degree and additive identities exist. Exemplars distinguish
  “too late”, “too little”, “universities, too” and “too noisy”. Case 089 still
  requires actual scope/negation/degree review; selecting an adverb POS alone does
  not choose among these meanings.
- Spanish `visit`: `visita` (76), `visitar` (16), `visitas` (2). The `visitar`
  exemplar contains “opportunity to visit”, so an existing verb alternative is
  available for case 088. Its dictionary link labels meeting someone, while the
  exemplar visits internet content: the explicit dictionary label is not itself
  the contextual gold sense. More starkly, `visitas` is dictionary-linked here as
  a noun but its retained exemplar uses the finite verb “sites you visit”. This
  is direct evidence that a surviving shared noun identity can misdescribe the
  aligned occurrence.
- Names: `fruits` retains ordinary noun meanings (`frutos`, `matunda`) despite
  case 029's title “Fruits Baskets”; `flash` retains an identical Spanish common
  noun face, which is not useful immersion or superhero-name evidence. `tech`
  has no shared-complete candidate. Names require protection/abstention; ordinary
  lexical availability does not establish a translated name.

These are diagnostic inspections of retained examples, not new target patches.
The full raw pool can contain further candidates lacking shared-complete backing;
absence here is scoped to the complete-backed pool, not to a language as a whole.

## Consequence and execution limits

A sparse selector can test choosing existing Spanish musical/verb/degree
alternatives. Its evaluation must separately report candidate absent, source role
unresolved, same-POS sense unresolved and incompatible target form. Count correct
selection only after contextual review; abstention is the necessary outcome for
missing or unresolved data. Broad source POS alone will not distinguish musical
play from game play or degree too from additive too. Do not promote unique
remaining links to truth, or infer corpus sense labels from dictionary agreement.

Execution finished in 60.91 seconds, pinned to one CPU, with a 256 MiB address-space
ceiling and 180-second alarm. Admission verified the local 8 GiB reserve plus
32 MiB output allowance. Output stayed below 32 MiB; no original file was changed.
The receipt's `max_rss_bytes` is **not a valid process peak measurement**: Linux
`getrusage` in this launcher reports an inherited high-water value of about
2.6 GiB. A separate trivial Python diagnostic reproduced 2,725,388 KiB from
`getrusage` while `/proc/self/status` reported only 11,768 KiB VmHWM and 31,036 KiB
VmPeak. A live inventory observation at 35 seconds was 116,548 KiB RSS; the enforced
address-space limit bounds subsequent allocations, but the exact inventory peak
was not captured independently. Preserve this measurement gap and the original
receipt; do not rerun the inventory to replace it. Future bounded scripts should
record `/proc/self/status` VmHWM and the active limits as well as `getrusage`.
