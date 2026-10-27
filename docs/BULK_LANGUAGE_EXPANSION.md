# Bulk local language expansion — 2026-10-27

The active expansion uses the full retained dictionaries and direct parallel
text. Storage is a capacity to use, not a reason to limit the catalog to a few
handwritten examples. The accepted app default remains bundle 022 until the
broader data passes meaning review and production delivery checks.

## Noun forms and native qualification

Revision 007 contains eleven SQLite shards totaling **1,677,676,544 bytes**.
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

These are authoring and native component results. Production still needs a
streaming signed installer for the larger shards, a verified catalog provider
in live conversations, further meaning/transliteration assessment, and live
speech/interaction checks. No release-ready flag, production language default,
store status or subscription configuration changed in this expansion.
