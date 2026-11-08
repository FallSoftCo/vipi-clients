# Dormant Japanese reading component

`JapaneseReadings` is a reusable native component with no production call site.
`SentenceReadings`, displayed message text, the immersion matcher and the speech
adapter remain unchanged. Callers must use only a non-null `Result.reading` as
an accepted complete candidate; diagnostic pieces do not authorize partial
proper-name readings.

The component uses the existing pinned Kuromoji dictionary and its pronunciation
or reading fields. An unknown token may use its written surface only when the
entire NFKC-normalized candidate is kana/prolonged marks; source text is never
normalized. Pieces retain the native, surface-kana or copular-rule basis. A
narrow native POS rule handles standalone `何` immediately before a copula;
particles, gaps, quotes and larger dictionary words are excluded. It joins
adjacent inflection and dependent-word pieces before
the deterministic native kana-to-Latin transform, so a small tsu at a native token boundary
can see the following consonant. It introduces no phrase replacement table.
The exact grouping and rejection rules are frozen in
`qa/immersion/japanese-reading-r03/rules.json`; r02 remains the prior control.

Protected identifiers and code remain opaque. Generated word boundaries are
outside literal spans. A broad URL or handle containing undelimited Japanese may
be an internationalized identifier or prose; the component preserves it and
withholds the full reading. This intentionally loses some available readings,
including the earlier URL immediately followed by `です`, rather than guessing
where identifier data ends. Explicitly delimited ASCII URLs remain supported.
Unknown Japanese outside opaque code and unsupported kana sequences also
withhold the full candidate.

The r04 candidate replaces Android ICU with `KanaRomanizer`, a small Kotlin
implementation of the factual kana correspondences in ALA-LC's 2022 charts A/B.
The primary PDF SHA-256 is
`0a28f06ddbdd8353d691e6c650ebd986c1ae874119ca08c6ecc6a2d1502b5cd8`;
printed pages 33–34 were visually inspected. Existing `wo/wi/we` display spelling
is retained, so this is not a claim of full ALA-LC catalog-style compliance.
Explicit prolonged vowels use macrons; syllabic n is separated before vowels/y;
unsupported geminates and marks are withheld rather than silently deleted.

Kana clusters normalize only in an analysis copy, with original UTF16 boundary
mapping. Composed/decomposed kana may therefore reach the same native dictionary
entry without changing source messages or identifiers. An internal boundary in
an indivisible transformed cluster is invalid for source-piece emission.

The component has no API-29 ICU dependency and is compiled for the app's API-28
minimum. Actual native qualification still uses API 35; host JVM8-target
compilation is not proof of execution on an Android 9 device. Earlier r02/r03
ICU captures and their explicit API-28 limitation remain retained controls.

The original r02 protocol has 246 rows: the previous 12 examples, all 106 existing
authored Japanese sentence readings, all 100 distinct Japanese source messages
in a retained XPersona validation diagnostic, and 28 new general controls. The
retained corpus is human-adapted persona role-play, not an untouched test or a
sample of spontaneous private chat. Original source, licenses, deduplication and
ordering hashes are bound in `protocol.json`. No target translations are used as
gold. Authored Latin readings are retained for review rather than exact-string
grading across different spelling conventions. The separately frozen r03 keeps
those rows unchanged and adds 24 kana/copula contrasts, totaling 270. Contextual
Han failures such as `一人` and `皆無給` remain documented; candidate availability
is not a correctness measure and authored sentence readings remain authoritative.

`JapaneseReadingsDeviceTest` takes the protocol's SHA-256 as the required
`protocol_sha256` instrumentation argument, reads
`files/japanese-reading-candidate-protocol-r03b.json`, and writes every result to
`files/japanese-reading-candidate-003.json`. This uses the r03 whitespace-only
assertion erratum: `ずぴらみこ` and `何だ` may have different native word grouping,
so those two checks ignore generated spaces. The 270 source strings and the
component are unchanged; the earlier failed assertions and outputs are retained.
It records first/warm timing,
process-memory observations, exact source pieces, native tokens, frozen control
results and explicit failures. Native capture and language review are separate
gates. No audio, model download, translation call or store submission is involved.

The API-35 r62 replay passes its 270 mechanical/control rows and produces exactly
the same readings, pieces, issues and native tokens as the r61 app run. The
retained XPersona set has 99/100 available readings after the kana-only fallback;
the remaining `イェール` conversion is withheld. Known Han context mistakes,
including `一人` and `皆無給`, remain. These are diagnostic availability and
mechanical results, not a 99% semantic-accuracy claim or production acceptance.

The frozen r04 converter comparison keeps all 592 distinct native-derived kana
sequences and 60 controls used for the upstream-library comparison. It also
checks composed/decomposed source equivalence and malformed-kana abstention.
Both the old Kotlin WanaKana port and upstream JavaScript defaults are retained
as negative comparisons; neither was added as an application dependency.
See `qa/immersion/japanese-reading-r04/rules.json` for primary source provenance
and the deliberately limited display policy. Native outcomes are in retained
r63 receipts; no production reading caller is enabled by this component.
