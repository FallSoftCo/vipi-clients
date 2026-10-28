# Noun context alternatives — 2026-10-28

The accepted bundled lexical catalog remains 009. This English–Spanish
experiment is isolated QA data; no language download or store release changed.
Majority coverage and 90% useful immersion in every supported direction remain
unachieved.

## Native checkpoint

Android 512 passes fixture 510: the prior 83 present-verb cases plus 16
deliberately wrong noun meanings, word fragments, grammar and sentence-boundary
cases in both directions. The noun additions are restricted to complete noun
forms in modes 1/2, intersected with both actual forms' eligible dictionary
relations. Existing number, name, compound, reading and sentence checks remain.

| Diagnostic | Messages before → after | Selected spans before → after |
| --- | --- | --- |
| 20 authored English→Spanish captures | 14 → 15 | 23 → 28 |
| Their 20 reversed pairs | 15 → 15 | 30 → 32 |
| 200 retained real English SMS→Spanish | 80 → 81 | 108 → 113 |

Android 607 supplies the final SMS result. No previously selected span is lost.
The five SMS additions are opinion→opinión, centre→centro, room→habitación,
Sunday→domingo and session→sesión. Only the first makes a previously empty
message immersive. This is improved depth, with very limited additional reach;
it is not a population or meaning-accuracy score.

noun-native-review-001 retains 13 contextual author assessments: seven captured
additions, books→libros in a tense counterexample whose verb remains withheld,
and the five SMS additions. Football→fútbol reflects the intended association
football sense of that authored example, not a universal dialect equivalence.
The reviews do not certify all training rows or whole-message translations.

iOS 512 passes the same 99 cases with exactly the Android spans. Its SMS
replay 607 rises from 83 to 84/200 messages and 111 to 116 spans, adding the
same five spans. The three prior iOS-only spans remain; noun-native-sms-parity-001
retains their exact differences, so complete SMS parity is not claimed. iOS 608
with the old witness exactly preserves all 200 prior iOS outputs.

Android bundled replay 016 completes all 602 directed cases with accepted
catalog 009: 256 messages remain nonempty and selected spans rise 359→365.
Six Portuguese→English spans are recovered without losing any prior span:
livro→book twice, ler→read, fatores→factors twice and parte→part.
noun-native-review-002 assesses these and the three prior iOS differences.
This broad replay uses no experimental noun data.

The initial bundled comparison keyed outcomes only by message ID, collapsing
602 directed cases to 330 IDs. It is superseded by noun-bundled-comparison-002,
which checks each (ID, source, target), exact geometry and all fixture entries.
Its complete comparison confirms the six additions and zero removals.

## Data and reproducibility

build_noun_context_filter.py selects 156,041 English and 62,077 Spanish
spellings from the complete eligible explicit noun forms. It does not use
evaluation messages. The source filter is 4,657,152 bytes, SHA
f14a84bd685cee25c6f9492b1c055f1f882c9008f9f3515928e02c7626644fb0.

The filtered observation pass reuses the exact three existing English–Spanish
context corpora, their dictionary release, exclusions and disjoint sentence
identities. Only source spellings are filtered. Every matching existing valid
legacy aligned counterpart, including competing and unresolved counterparts,
remains. This is not proof of contextual part of speech or exhaustive word
alignment. Synthetic counterexamples verify the denominator and reversed-pair
query filtering.

noun-observations-001 retains 33,236,125 observations from 2,943,398 distinct
reference spans, 1,216,942,080 bytes, SHA
3c69a203ea96031e9edec742c04b506cc46f91b41155104c8b88852a46f697d8.
The pass took 1,152.72 seconds under a 4 GiB storage reservation.

The alternative compiler preserves one vote per source sentence. Conflicting
translations intersect, unknowns remain negative, each accepted relation needs
three source sentences and at least 98% reference agreement, and the actual
counterpart needs three supporting sentences. Reference agreement is not
semantic correctness. A distinct noun policy/table prevents applying these
relations to arbitrary verb forms.

context-witnesses-506 contains 1,132,836 noun alternatives from 12,105,508
contexts; 5,620,545 unresolved observations remain in the denominator.
The 582,770,688-byte artifact has SHA
638e7ebac551091d60bf2a05bd0f84fedc0a7359b2af7d6d109d7fd2ec5fb9bb.
Compilation took 230.41 seconds under a 1 GiB reservation. Exact bidirectional
SQL comparison proves that all existing witness, present alternative and
present example rows are unchanged. This authoring/QA artifact still contains
evidence examples; its size is not a promised mobile pack size.

## Lookup regression found and corrected

Initial Android 606 added five SMS spans but lost three old spans in two long
messages. The query fetched unrelated context cues and exceeded its unchanged
8,192-row bound: even a single-token subset fetched 11,260 and 9,243 rows,
where only 147 and 206 matched words in the respective messages.

The native readers now query only possible context windows in the actual
original text. French elision and Japanese compound windows are retained.
This changes neither corpus denominators nor acceptance thresholds. Android
607 restores all three spans; 608, using the old witness data, exactly preserves
all 200 prior SMS outputs. See noun-irrelevant-cue-overflow-001.json and
noun-reader-cue-filter-parity-001.

## Operational receipts and remaining work

- Android builds 001/002/003 are retained; installed source is build 003.
- APK update 014 failed for insufficient emulator space and restored its exact
  QA staging. Rebooting only the owned emulator reclaimed Android package
  cleanup space. Update 015 succeeded while the checksum-verified experimental
  witness was temporarily removed, then restored; no account, key, message or
  translation-model reset occurred.
- Bundled replay 015 stopped at 460/602 when Android reclaimed cache scratch
  under disk pressure. It recorded no meaning failure, but is incomplete.
  The production reader uses noBackupFilesDir; this was QA scratch in cacheDir.
- iOS build 510 compiled successfully but its fixture symlinks exposed link
  sizes to the native file validator. Exact shard hardlinks fixed staging;
  511/512/607/608 then passed. No product file validation was weakened.
- decoded-dictionary-019-eviction-001 verifies every old decoded shard against
  retained compressed bundle 008 before removing the redundant decoded copy.
  It reclaimed 1,724,116,992 bytes; sources, catalog, compressed rollback and
  accepted 009 remain.
- retained-sms-lexical-gaps-002 identifies unselected non-grammar dictionary
  relations in 82 of the 120 previously empty SMS messages. They are
  unqualified possibilities, not 82 missing correct mappings. Many other
  messages contain informal spelling or poor whole translations.

Next work must improve ordinary conversational phrase and adjective coverage,
qualify useful extensions across the other languages including Swahili, and
measure meaning and immersion depth on broader conversation material.
