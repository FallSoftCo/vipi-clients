# Present verbs and contextual alternatives — 2026-10-28

This is isolated QA data. The accepted bundled lexical catalog remains **009**,
SHA 6b8040ae0eacb82dded24d9cf948649551195165d3d1c12a085e17e02e847300.
Majority coverage, 90% in each direction, independent meaning accuracy and
store readiness have not been achieved.

## Latest native checkpoint

Android 508 and iOS simulator 508 both complete the 83-case fixture: 40 captured
conversation pairs, ten authored/reversed personal clauses, and 33 negative
grammar/meaning/boundary cases. Android and simulator 605 also complete the
same retained 200-message SMS replay. The Mac went offline after these tests;
the last two raw simulator reports remain on that Mac, with completion hashes
recorded in present-native-review-002. Their final cross-platform comparison is
pending transfer. Earlier family/reciprocal reports were retained centrally.

| Diagnostic | Messages with immersion before → after | Spans before → after |
| --- | --- | --- |
| 20 authored English→Spanish captures | 13 → 14 | 17 → 23 |
| Their 20 reversed Spanish→English pairs | 15 → 15 | 22 → 30 |
| 200 retained real English SMS→Spanish | 78 → 80 | 105 → 108 |

No previous selected span is removed in these comparisons. The real-message
additions are miss→extraño, need→necesito and love→amo in two messages. The
83-case replay also proves the expected personal-clause outputs in both
directions, including You need me / Me necesitas and She needs you / Te necesita.
This is a bounded improvement; 40% message availability on this SMS diagnostic
remains far below the product target, and availability alone is not useful-depth
or meaning-accuracy acceptance.

The new fallback allows grammatical cues only when **every** word in the
surrounding short clause is the full finite verb or a listed personal pronoun
on both sides. Unknown words, adverbs, negation and auxiliary constructions do
not disappear from this check. Four assessed transparent units (I miss you,
I love you, love you, te amo) can release their complete lexical verb while
other compound guards remain. English need's blanket grammar flag is bypassed
only for the finite verb inside this exact bounded personal-pronoun context;
nominal need, need not, need to, wrong persons and past targets remain withheld.

present-native-review-002 records 27 contextual author assessments across the
captured additions, ten personal-clause cases and three real-message additions.
It supersedes revision 001, whose comparison mistakenly filtered out the
separately labelled reversed captures. Neither revision claims independent
review, population accuracy or release readiness.

The compiler's repeated dictionary scans were replaced by one relation map per
language and indexed surface lookup. The same build falls from **2,090.85 s to
30.33 s (68.94×)**. semantic-alternative-equivalence-001 verifies exact equality
of every witness, alternative and evidence-example row in both directions.
The whole files differ because compiler provenance metadata differs. The
original compiler is retained in semantic-alternative-compiler-001.

## Changes and limits

The exact-form compiler adds 109,131 supplied positive present forms:
English 17,114, Spanish 36,094, French 23,322, German 12,372 and Portuguese
20,229. It classifies supplied English heads without generating spellings.
Italian is excluded because upstream internal stress marks are not ordinary
spelling. Only English and Spanish have the new native context qualification.

Independent Kotlin and Swift readers preserve exact spans, person, explicit
pronouns, possessive/noun evidence, tense conflicts, sentence alignment and
actual translated forms. English auxiliary questions cannot become positive
present assertions. A bounded list of ordinary verb/preposition complements
can pass phrase protection only with nearby lexical evidence. “Work out”
remains protected. No new data is bundled or served to users.

The alternative index groups explicit shared dictionary relations. Each source
sentence casts one vote despite multiple translations; unknown/competing
targets remain in the denominator. Each relation requires three source
sentences and 98% agreement, and each exact counterpart needs three supporting
sentences. Different vote sets are not unioned. Native readers intersect
candidate relations with both actual forms' eligible links. These are candidate
dictionary relations, not asserted true contextual sense labels or measured
semantic accuracy. Previous witness rows remain exactly unchanged.

The reciprocal-context path passed the bounded native fixture. It requires an
already accepted nearby lexical mapping connecting both sentences, original
sentence boundaries, and the same finite-verb checks. A context word occurring
only in the translation is insufficient.

## Actual conversation results

The 100-case protocol contains 20 authored situations in five target languages
captured through actual offline ML Kit. Six whole-translation concerns are
recorded in its author review. It is diagnostic material, not representative
chat or an independent accuracy sample.

Initial Android run 501 added **zero** spans in the 20 English–Spanish cases:
baseline and candidate both had 13 messages with immersion and 17 spans.
Inventory expansion alone did not improve that sample.

The complement change, Android and iOS simulator 502, adds “live → Vivo” in
“I live with my parents.” Both pass the same 56 cases: 20 forward captures,
their 20 reversed pairs, and 16 deliberate grammar counterfactuals. Reverse
pairs are reused translations, not fresh native translations.

The alternative index, Android and simulator 503, additionally selects
“drinks → bebe,” “learn → Aprendo,” and “help → Ayudas” in the forward sample.
Reverse selections include speaking, writing, eating, washing and carrying.
These mappings now have their exact author assessment in present-native-review-002.

The broader Android 600 replay uses **all 200** retained English SMS messages
and their actual stored offline Spanish translations, with no lexical case
filter. It produces **no new present-verb substitutions**. Exact baseline
comparison is in present-sms-family-comparison-001.json. This failed
generalization must not be concealed by the easier authored examples. The SMS
messages were previously inspected and are not untouched acceptance material.

## Provenance and reproducibility

- lexical-present-verbs-001 catalog SHA:
  b113475a50d7ddf5eed24f776d6aad024df07e1d7e2f0650cce3403beb6dc391.
  Release f7093f99b61c1c3c422ede2f10b6930bdeabbedee2f814a0bb624ebc9b89dd24.
- present-verb-context-pilot-001/compiler-source preserves the exact extractor.
  Tatoeba, PGV and MASSIVE contexts and source corpus receipts remain.
- context-witnesses-present-pilot-003: 428,068,864 bytes, SHA
  956d32fb5960b42b2fb5e96aa9ae573baae79dbd403f7f0bf33909d2e29e3084.
- present-observations-001: exact 3,736,391 present-source observations,
  including all competing targets, 154,009,600 bytes, SHA
  82275af479b68e9efcdf057b9e85bf1a2a2a99db3bf5dd12b84b865a4b58aa24.
- context-witnesses-503: compact 63,062,016-byte QA baseline.
- context-witnesses-504: 106,130 alternatives from 1,086,587 contexts;
  44,075 unresolved observations remain negative evidence. 117,338,112 bytes,
  SHA 61c34e33af3b5ae570b0bc3ec1a69d3b9ee8324b0f7220186fd517aa9c3b8e20;
  2,090.85 seconds.
- present-native-source-006 preserves the alternative reader before the next
  reciprocal-context change. Fixtures 501/502/504/600 and native reports pin
  exact inputs, witnesses and installed APK hashes.

The frozen corpus extractor predates the additional English auxiliary-question
veto. Current Python source and both native readers include it. The retained
snapshot is unchanged; corpus references do not certify runtime grammar.

The initial readers with accepted bundle 009 retained all outputs on the
602-case Android/simulator baseline. That does not qualify later rules.
No new physical-device or listening acceptance is claimed.

## Storage and runner corrections

The full witness build's 2 GiB declaration underestimated its 3.19 GB
observation database plus 428 MB witness output. Future equivalent builds
need about 4.5 GiB including temporary output. The host's 8 GiB reserve remained
enforced. The exact present observation subset was verified before retiring
the superseded full observation scratch database.

Retirement receipts preserve the source/provenance and exact decisions:
context-agreement-intermediate-retirement-001,
obsolete-bundled-pack-retirement-001,
superseded-dictionary-retirement-002,
superseded-witness-retirement-002 and present-observations-001. Accepted
bundle 009, rollback bundles 007/008, editable compilers and source corpora remain.

An owned-emulator reboot released stale installation space. Reproducible QA
shards were temporarily removed and checksum-restored; models, account,
messages and keys remain. Dedicated QA builds use x86_64 only.

The initial simulator runner read the old pre-install container UUID. The
actual 56-case test passed and its report was recovered from the new container.
Its stale owned control was removed; prior-control restoration for that one
run remains explicitly unverified. The corrected runner resolves the current
container and durably backs up/restores controls. The next 56-case run completed
normally with that correction.

The redundant decoded lexical-shards-018 files were later evicted only after
streaming verification that bundled-lexical-007 preserves their exact bytes,
checking all compressed/uncompressed hashes and excluding active consumers.
The compressed rollback, catalog, sources and receipts remain. This reclaimed
1,696,391,168 bytes; decoded-dictionary-018-eviction-001 is the receipt. Restore
those old files from their recorded compressed entries under storage admission
if historical reproduction needs them; do not treat their absence as missing
source data.
