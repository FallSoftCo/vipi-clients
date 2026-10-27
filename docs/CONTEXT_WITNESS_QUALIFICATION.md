# Native contextual dictionary qualification — 2026-10-27

Latest bulk expansion and native run 018: [BULK_LANGUAGE_EXPANSION.md](BULK_LANGUAGE_EXPANSION.md). This is experimental language data; the default catalog remains bundle 022.

The corpus expansion is now executable in native Swift and Kotlin. This is
experimental selection evidence, not a promoted production language pack.
The default application catalog remains bundle 022.

## Data

The eleven revision-006 lexical shards occupy 1,586,442,240 bytes. Witness
revision 002 adds 300,105,728 bytes and 1,447,899 contextual rules in 86
directions with sufficient direct reference evidence. All 110 directions were
requested; missing evidence does not produce an inferred translation pivot.
Its SHA-256 is
`e08aabd632b041283536a4f7163eeccb50444dfe3d445f6039d72e7cbdeb5d93`.

`language-packs/build_context_witnesses.py` reads the complete development
context index. It deduplicates competing dictionary sense rows by actual
source/target focus, counts distinct source sentence IDs, and requires at least
three supporting references with at least 98% agreement among observed target
alternatives for the written word and cue. This is reference agreement, **not
a correctness probability**. Three attributed examples per rule and source
contributors remain available. Exact duplicate-text auditing of prototype 001's
retained examples found none; it is not a complete normalized-text independence
audit of 002.

The full build processed 3,571,921 distinct focus spans and 31,735,647 distinct
observations, retaining 1,730,401 attributed sentence IDs. It took 907.01s on
OZZZ-OS under 6 GiB storage admission. SQLite integrity, hash and row counts
were independently checked. The native payloads total **1,886,547,968 bytes**;
the large authoring corpus and observation databases are not client payloads.

## Native selection

`ContextWitnessLookup` uses indexed SQLite queries, a matching dictionary
release, bounded result sets and a cue in the actual source clause, within six
native words. It never generates translations. `LexicalConcordance` retains
dictionary links, all competing target claims, number/form geometry, compound
protection and mandatory supplied readings. The context fallback currently
accepts whole source forms only; the strict path also supports explicitly
attested carrier stems.

The first prototype incorrectly admitted grammatical words such as “when”.
Later revisions retain grammatical source evidence, including competing
alternate-script analyses. A differently capitalized surname no longer erases
a supported lowercase common word, but actual names remain protected even
when the supplied whole translation mistranslates them. Exact message and
translation scopes bind every emitted mapping.

The final snapshot is `artifacts/native-lexical-source-013/receipt.json`.
Native run 012 uses that snapshot, witnesses 002 and fixture 007. All 15,342
cases pass on both platforms, including prior meaning/scope negatives,
Swahili carriers, compounds, grammatical aliases and name guards.

| Reused captures | Android baseline + additional = union | Physical iPad |
| --- | ---: | ---: |
| SMS, 3,600 | 651 + 345 = 996 (27.67%) | 662 + 349 = 1,011 (28.08%) |
| Multi3WOZ, 3,600 | 1,613 + 484 = 2,097 (58.25%) | 1,635 + 479 = 2,114 (58.72%) |
| XPersona, 2,700 | 575 + 432 = 1,007 (37.30%) | 595 + 424 = 1,019 (37.74%) |
| Explicit Swahili, 1,910 | 151 + 26 = 177 (9.27%) | 154 + 27 = 181 (9.48%) |

These are separate-path unions, not integrated app results. The English–Spanish
SMS subset reaches 46.0% on Android and 47.5% on iPad. Thirty-eight broad-path
cases differ between platforms; complete parity is not established. Median
lookup/alignment is 3.344–7.904ms by dataset on Android and 2.387–5.595ms on
iPad, excluding translation.

Author review of all 55 newly selected spans in the narrower run 009 accepted
their focus mappings. A later direction-stratified run-010 review inspected 79
messages across 40 directions and rejected two grammatical Chinese aliases;
snapshot 013 fixes those cases. These are author reviews, not independent
semantic precision estimates. Whole-message translation and spoken reading
quality are not certified by a correct written focus.

## Fresh reserved evaluation

`qa/immersion/prepare_reserved_lexical.py` sampled up to 100 distinct reserved
translation-graph components per direction, with separate deterministic
component/link ranks and no vocabulary filter. It uses only direct publisher
reference translations. Every selected endpoint is absent from the training
context index. Swahili duplicate groups touching development, disconnected
duplicates and editorially flagged sentences are excluded. Hashes bind the
original exports, the source snapshot frozen before sampling, and fixture 008.

The fixture contains **8,410 pairs across 102 directions**, including Swahili.
Eight directions lack direct reserved references. The smaller Swahili directions
have as few as two cases; they cannot establish representative pair coverage.
The fixture manifest SHA is
`eeba3578c08a1d13ee4ea1c6d7c9b4a7578fa862d283f6075d9681cffe28a316`.

Native run 013 passed on Android in 140.000s and the physical iPad in 74.649s.
The selector was unchanged after its pre-sampling snapshot.

| Reserved references | Android | Physical iPad |
| --- | ---: | ---: |
| Baseline messages | 1,339 (15.92%) | 1,361 (16.18%) |
| Additional messages | 1,622 | 1,639 |
| Separate-path union | 2,961 (35.21%) | 3,000 (35.67%) |
| Broad selected spans | 2,923 | 2,947 |
| Median / p95 lookup, ms | 5.988 / 17.521 | 3.901 / 8.839 |

Forty-four cases differ between platforms. Passing mechanics and availability
on reference sentences do not establish majority chat coverage or independent
meaning accuracy. They also exclude native translator quality, language
classification, model download and end-to-end audio latency. Reserved results
were summarized after the test; an overly broad diagnostic print also exposed
some selected word spans. This evaluation remains evidence for the frozen
snapshot, not untouched material for future selector tuning.

Raw reports and analyses are `artifacts/lexical-{coverage,summary}-{android,apple}-013.json`.
Compiler tests cover distinct-support counts, ambiguity, clause boundaries,
UTF-16 offsets, attribution and hash binding. Reserved sampler tests cover
duplicate isolation, direct-only links, editorial exclusions and source hashes.

## Remaining product work

Native run 014 now exercises the actual catalog composition method with broad
entries supplied explicitly. It passes all 15,342 cases on Android (361.811s)
and the physical iPad (228.461s xcodebuild operation). No accepted baseline span
is lost. Combined message availability equals the separate-path union in each
dataset in the run-012 table above. Combined output has 125 platform differences;
the isolated broad path still has 38. The method retains all primary claims and
native guards, refuses additions overlapping accepted source or target ranges,
requires exact current-message scopes and applies density once. Four new core
tests on each platform cover ownership, competing evidence, density, stale
scopes, identifiers and mandatory readings; both complete core suites pass.

This is native catalog-component integration, not an installed production
download or an end-to-end live chat acceptance. Production delivery needs
streaming installation and signature/rollback handling for files larger than
the existing 64 MiB pair-pack installer. Broader semantic/readings assessment,
low-resource evidence expansion, cross-platform differences and live chat/voice
qualification remain open. No release-ready flag or app default was changed.

The temporary reserved-corpus working clone was retired after both reports
completed, hash verification and a root open-consumer check. Its 1,761,800,192
bytes were reclaimed; the original archived source and receipt remain intact.

## Additional source acquisition

The [Parallel Global Voices distribution](https://nlp.ilsp.gr/pgv/) provides
all 55 unordered pairs in the eleven-language set, including ten Swahili pairs.
Acquisition 001 pins 417,457,947 compressed bytes / 1,679,917,800 archive-member
bytes, source page, archive SHA-256 hashes, member sizes, notices and citation.
The publisher distributes its alignments under CC BY 4.0; Global Voices content
retains its attribution license. These are automatically aligned translated
articles, not independently accepted chat mappings. The TMX header and archive
README identify mALIGNa, whereas the index page says hunalign. The retained
source evidence preserves that discrepancy. No PGV row has entered the witness
build or native results above. Import needs duplicate/evaluation exclusion,
source attribution and separate qualification.
