# Context capitalization safety — 2026-10-28

The native readers now distinguish ordinary sentence capitalization from
internal capitals and acronyms. No production language data changed; the
accepted catalogs remain lexical 009 and reviewed phrases 022.

## Error and correction

New authored probes exposed three wrong selected spans in both previous apps:
Food→comida in the name-like “I called Food,” its reverse, and habitación→ROOM
for an explicitly named project code. The noun experiment did not introduce
these errors. Old reports 513 retain the failures.

Dictionary matching now permits only an initial-letter case change at a
sentence boundary; internal capitals cannot borrow a lowercase analysis.
Context matching uses the same written-case rule as the strict dictionary path.
Opening punctuation, including Spanish ¿/¡ and quotes, is allowed at a
sentence start but cannot excuse a mid-sentence name.

Reviewed noun aliases are constrained using the two exact existing common-noun
case policies in their retained author provenance. Only those explicitly
generated variants, only bare units, and only en/es/fr/it/pt/sw are affected.
German capitalization and other authored phrases keep their existing rules.
No heuristic based on record IDs is used. All source meanings and repeated
occurrences still enter ambiguity resolution before the final case veto.
The original signed data and per-record evidence remain unchanged.

## Native results and cost

Final Android/iOS runs 515 pass the same 131 cases with identical 115 selected
spans. The three wrong spans are absent; this case probe supplies no additional
coverage gain. Both native core checks pass, including contrary meanings,
reverse-direction names and opening punctuation.

The final SMS replay is 610 on both platforms. Android retains immersion in
81/200 messages and changes 113→110 spans. iOS retains 84/200 and changes
116→113 spans. Both add Haha→Jaja and withhold four previously valid mappings:
Exam→examen, today→Hoy, music→Música and school→Escuela. This is an explicit
false-negative cost of stricter casing, not a precision percentage or coverage
improvement. Three pre-existing SMS platform differences remain.

Android broad replay 017 completes 602 directed cases: 256 nonempty messages,
364 spans versus 365 before. The valid مطعم→Restaurant mapping is now withheld
because Restaurant is capitalized inside the retained English translation.
iOS broad replay 018 also completes 602 cases: 257 nonempty messages, 364 spans.
Against its older pre-query-fix run 014, it gains the six reviewed Portuguese
spans and loses Restaurant. The two baselines therefore differ in code revision.

context-case-review-001 records exact additions, corrected errors and valid
withdrawals. These are author assessments, not independent accuracy acceptance.
The data does not establish majority or 90% conversational coverage.

## Reproducibility

- Final native sources: artifacts/context-case-source-002/receipt.json.
- Android builds 001 and 002 pass; final installed APK is build 002.
- Final app APK SHA: f81a0dee3c1ff9686b41a63270c80439708804cb0ca8f8d61f7903edc37b7be4.
- Fixture 511 appends 32 authored probes to fixture 510. Its cases SHA is
  32540e64fde613067bae1b6a7d5e43e33783d9b057453deb686e70cc2dd9af26.
  prepare_context_case_regressions.py reproduces those cases from the pinned
  baseline and tracked context-case-regressions.json.
- run-lexical-candidate-android.py verifies both installed package hashes,
  shard hashes, witness and cases before accepting a native report.
- qualify-context-case-android-001.py temporarily frees only the exact
  reproducible QA witness for installation/broad replay, then restores its
  hash in a finally block. Account data, keys, messages and models are preserved.
- Shared disk admission delayed Android builds. Only the idle owned Vipi
  emulator was stopped to release its reservation; it was restarted under
  storage-build and completed qualification. No unrelated workload was stopped.

The next coverage work must address real missing word/phrase meanings and
grammatical forms across languages. More byte volume or passed regressions
alone does not meet the immersion standard.
