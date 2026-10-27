# Broad lexical coverage

The 2026-10-27 expansion replaces small manual vocabulary batches as the main
data acquisition method. The existing app bundle remains the accepted native
checkpoint while the broad dictionary path is qualified. Counts below are
dictionary evidence, not linguistic acceptance or demonstrated chat coverage.

## Source inventory

`language-packs/build_lexical_inventory.py --all-native` scans the complete
pinned English Wiktionary extraction for English, Spanish, French, German,
Italian, Portuguese, Arabic, Chinese, Japanese, Korean and Swahili. It preserves
English translation sense groups, native entry identities, native glosses,
explicit lemma references, supplied inflections, usage tags and source URLs.
Separate entries and etymologies are never merged solely by spelling.

Complete inventory 003 contains 142,447 bilingual sense groups, 5,055,081 native
entries, 6,093,735 native senses and 13,265,782 supplied forms. Its SQLite file is
4,428,693,504 bytes, SHA-256
`8c97e9de2ce8e94ce9754475a85eb27cd956ee0ba69491fe270376e3177ceb17`.
This is the build inventory; users download individual compiled languages.

`build_native_redirects.py` separately preserves exact upstream alternate-script
redirects. Complete supplement 003 contains 69,618 Japanese and 127,553 Chinese
redirects. It records 133 unsupported lexical forms as rejected evidence.
Duplicate supplied links are deduplicated. Its 6,762,496-byte database has SHA
`d3020598f51d625dd096697edd629061655119df361db0b935e96872a61bc40b`.

Both inputs retain the full 11,121,531-row source identity and upstream SHA
`244dcdc56868d81dc60e3820657780c06fac2729a90e2c5ffbfa13e6f9ecad1d`.
Wiktionary contributor attribution and CC BY-SA 4.0 notices travel with the data.
Neither compiler copies example quotations, audio or IPA into the packs.

`build_native_gloss_links.py` recovers explicit native definitions missing from
English-side translation tables. Supplement 001 contains 254,059 direct links
to English, including 1,365 from Swahili. It requires a single short native
gloss, a uniquely identified English entry with the same part of speech, and
no unresolved usage restriction. Definitions remain separate native sense IDs;
they cannot serve as inferred pivots between two non-English languages.
The supplement is 36,163,584 bytes, SHA
`e24cfb9a5843e8395b3eee2f217d3d508251c301fef85058c03ddf1a4ed7b56f`.
For example, sema's native definition supplies “say, speak”; the English-side
translation inventory alone contains neither sema nor kusema. Existing native
romanizations are retained only when readable and unique; none are invented.

## Per-language compilation and lookup

`build_lexical_shards.py` emits one indexed SQLite file per language. Shared
source sense IDs join the two installed languages at runtime; pair Cartesian
products are unnecessary. `--language` supports rebuilding one language from
the same pinned inventory. Outputs are immutable revisions with file hashes,
compiler hashes, byte counts and provenance. Reusing an output directory fails.

`native_lemma_links.py` follows explicit form-of, alternative-form, canonical
form and alternate-script redirect evidence. It never guesses a stem by
stripping a prefix. Cycles, conflicting references, qualified aliases and mixed
lexical/form entries retain separate identities. Native short English glosses
can veto contradictory links; they are not a general sense classifier.

Examples exercising the linker include kusema→sema, kupenda→penda,
kujua→jua, ninapenda→penda and 欲しい→ほしい. The last relation is resolved
through the entry's explicit alternate-script backlink, preserving the
separate noun and surname entries for the same kana spelling.

The Swift and Kotlin readers use indexed native text windows, bounded result
sets, complete source analyses and actual full-message translations. They
require matching inventory versions and mandatory supplied Latin readings for
non-Roman target scripts. Grammar, named entities, compounds, identifiers and
ambiguous alternatives remain relevant negative evidence. The readers do not
generate a new translation or invoke a network model.

A release ID binds the complete source inventory, redirect supplement, direct
gloss supplement, shard compiler and lemma linker. Two languages from different
compiler/data revisions are rejected even if they share the same upstream
inventory. Query overflows abstain on both sides; truncated target analyses
cannot silently select a reading or sense.

## Evaluation

`qa/immersion/prepare_lexical_qualification.py` freezes the existing SMS,
Multi3WOZ, XPersona and explicit-Swahili native translation captures. It adds
deterministically selected dictionary-unit probes across all 110 directions,
known meaning/scope regressions and explicit Swahili carrier checks. Reused
diagnostics and dictionary-unit mechanics are reported separately. Corpus text
does not enter dictionary construction.

The first 1,142,284,288-byte shard revision compiled on both native platforms,
but Android qualification 001 failed its first Swahili carrier requirement.
That run exposed disconnected infinitives and inflected-entry identities;
it is not an accepted result. The partial report contains all conversation
rows, but an incomplete dictionary-mechanics tail. Later tests save every
meaning/behavior failure and complete the replay before asserting success.

Revision 002 fixes explicit lemma relationships and target lexical homographs,
but a preflight found sema still absent because its bilingual link was missing.
Its fixture was prepared, but no native pass is claimed. Revision 003 includes
the direct native-definition supplement. Its qualification remains separate
from the existing accepted application bundle.

### Native checkpoint 004

The eleven revision-003 shards total **1,587,359,744 bytes**, with 3,859,510
distinct indexed written forms counted separately by language. English is
195,907,584 bytes and Swahili is 12,034,048 bytes. Swahili has 5,108 headwords
with eligible lexical links; the other ten languages each exceed 10,000. The
full QA archive is 294,782,813 compressed bytes. Release ID:
`4b5cba46bdd7a0575b4aaeb3cac552339872c382ee1eb2d32fd5853daa0ca00f`.

Android 004 passes in 245.001 seconds; physical iPad 004 passes, with a 136.982s
xcodebuild test-operation duration. Both process all 15,335 fixture cases,
preserve supplied text and offsets, retain required readings, reject the 15
known meaning/scope regressions and pass three Swahili carrier positives plus
two negatives. A bounded target-phrase exception uses attested present-tense
person/number features; it permits the correct lexical focus within “I know”
without disabling arbitrary compound protection. The mismatched-person probe
remains withheld.

| Reused conversation captures | Android baseline + additional → union | iPad baseline + additional → union |
| --- | ---: | ---: |
| SMS, 3,600 cases | 651 + 82 → 733 (20.36%) | 662 + 83 → 745 (20.69%) |
| Multi3WOZ, 3,600 cases | 1,613 + 154 → 1,767 (49.08%) | 1,635 + 155 → 1,790 (49.72%) |
| XPersona, 2,700 cases | 575 + 289 → 864 (32.00%) | 595 + 280 → 875 (32.41%) |
| Explicit Swahili, 1,910 cases | 151 + 24 → 175 (9.16%) | 154 + 25 → 179 (9.37%) |

These are separate-path unions, not an integrated application result. Android
lookup/alignment medians are 3.1–6.6ms across the conversation datasets; p95 is
10.1–20.5ms. iPad medians are 2.2–4.3ms and p95 5.5–9.0ms. Translation was
reused, so these timings exclude translation and do not establish end-to-end
latency.

The 3,520 single-word dictionary probes cover all 110 directions. Android
actually selects spans in 101 directions; nine Arabic-source directions have
none, principally because competing entries and whole-form geometry/number
analyses are still unresolved. Both native outputs differ in ten of the full
15,335 cases. This is **not complete native parity, majority conversation
coverage, independent semantic acceptance, or release readiness**. The data is
still exercised by native QA and is not the application's default dictionary.

Receipts: `artifacts/lexical-summary-{android,apple}-004.json`; Android raw SHA
`6fec839f12a172cd5949a3f8b55fd3a63ae8d238f00d2dc267501c63704f1544`,
iPad raw SHA `dee2f60254ee23eb9e2345ff2c8580951f37f8bf0a063849c4196fe7905b28c6`.
Both bind manifest SHA
`f991b520975218ba26d7bddbafafaff8193b6eff9c48da7c7518474573e7127d`.
The failed Android 003 run is retained; its overbroad “I know” guard is fixed
in 004. No corpus text was copied into authoring to achieve that fix.

Coverage means messages with an actual selected span, measured on the native
readers. Source inventory size, pair counts and lookup speed are separate
metrics. Passing mechanics does not establish semantic precision. Broad
conversation acceptance, fresh untouched evaluation, app download integration
and release signing remain separate requirements.

## Storage and regeneration

Run substantial work on OZZZ-OS under `storage-build`, with a measured declared
peak and disk-backed temporary files. The full upstream extraction, receipts
and original source identities are retained. Closed research model weights
have verified Storage Box copies with original consumer paths preserved as
symlinks; `artifacts/closed-research-archive-001/receipt.json` records all hashes.
Rejected regenerable derived weights were retired. No model or stopped service
was restarted by this expansion.

Current PanLex licensing was checked at its primary license page on 2026-10-27.
The live page requires noncommercial use or separate commercial permission,
despite a stale search result describing CC0. No PanLex data was acquired or
added. The older Kamusi export also remains unimported pending exact license
provenance. These are source acquisition findings, not application changes.
