# Local vocabulary data

First source: FreeDict + WikDict English–Spanish 2025.11.23, 64,258 upstream headwords. Its own TEI header declares **CC BY-SA 3.0** and credits Karl Bartel, Wiktionary contributors and DBnary. The source archive is pinned by SHA-512 and size. This does not imply the same license applies to every FreeDict dictionary.

`build_pack.py` reads exact bounded archive members, verifies the declared license, retains attribution/license/header, removes grammatical function-word and proper-name entries by part of speech, normalizes source forms and creates SQLite mappings. It keeps all viable senses; the native context filter must abstain when translation corroborates more than one. It does not infer morphology, certify translations, or produce a frequency-ranked learning curriculum.

The immutable SQLite file and canonical manifest are covered by SHA-256 and a detached P-256/SHA-256 signature. Native installers must pin a release public key, verify the original manifest bytes and content hash, enforce bounds/schema/revision, and swap files atomically. The development signing key is private and must not be trusted by production apps. The included public key is for build verification; downloading a key alongside a pack is not a trust model.

The derived pack remains CC BY-SA 3.0. Distribute attribution, full license, original pinned source link, transformation source and a description of changes with public releases. Current outputs are engineering fixtures, not published or quality-qualified language packs. Do not use dictionary headword count as a language-learning efficacy claim.

Primary sources: https://freedict.org/documentation/ and https://freedict.org/freedict-database.json . Every added language needs separate provenance/license and contextual quality review.

## Ten-language sense catalog

`build_wiktextract.py` compiles the existing pinned Kaikki/Wiktextract extract into a local SQLite candidate catalog for English, Spanish, French, German, Italian, Portuguese, Arabic, Mandarin Chinese, Japanese and Korean. Both the full-source identity and the retained selection's size/SHA-256 are pinned in `sources/wiktextract-20261021.json`; the compiler verifies those pins and records its own hash. It does not download again.

English translation groups retain their original source line, source page, part of speech, explicit sense label, written variants, tags and supplied romanization. English→target edges are direct evidence; reverse edges remain reversed evidence. Cross-language candidates require a shared explicit English sense within the same source entry. They are derivations, not independently verified translations. Missing labels cannot join unrelated translations, and repeated English headwords/etymologies never merge across entries.

The compiler excludes grammatical function-word parts of speech, tagged legacy/error entries, specified non-Mandarin Chinese dialects and regional Arabic variants. Explicit Mandarin `cmn` entries map to the product's `zh` code. Chinese slash-separated written variants may be separated; multiple romanizations are never guessed or silently resolved. Original romanizations remain available alongside conservative Latin display readings. Missing, conflicting and context-sensitive readings still require abstention. No quotation/example/audio/IPA fields are redistributed in the catalog.

The complete initial scan contains 4,364,675 selected upstream entries. Its current catalog contains 142,195 sense groups and 950,674 term records in 292,921,344 bytes (279.35 MiB). All 90 directed pairs have at least 10,000 candidate source headwords; that is a data-coverage measurement, not meaning or immersion acceptance. A term record can repeat a word in different senses. There is no frequency-ranked curriculum. See the exact current revision's `receipt.json` for per-pair counts and reading coverage.

This schema-2 research catalog is intentionally rejected by the native installer. `export_bilingual.py` creates bounded schema-3 pair databases that the native installers accept after signature, hash, schema, integrity and revision checks. Exported senses, provenance and conflicting readings remain separate. The full 90-pair qualification export totals 1,450,356,736 bytes; individual databases range from 6,578,176 to 29,335,552 bytes. It uses an ephemeral qualification signing key that is not trusted by release apps. The source and transformed data use CC BY-SA 4.0; public distribution must include attribution, the full license and corresponding transformation source. The existing FreeDict pack retains its separate CC BY-SA 3.0 license.

Actual offline Android qualification installed all 90 signed pair databases and translated/aligned 540 corpus messages. Execution succeeded, but semantic acceptance failed: 368 messages had replacements; 14 directions had none; ML Kit's incorrect financial-bank translation in a river context was accepted by the initial matching rule. Arabic vowel-mark mismatch and inflected forms reduce coverage. These results are retained in `artifacts/bilingual-android-pipeline-001.json`, with a complete observation review generated by `qa/immersion/review_pipeline.py`. Signature validity, dictionary coverage and test execution do not establish meaning accuracy. Context correction, Arabic normalization, held-out evaluation, actual Apple translation, release signing and download/removal UI remain release gates.

Compiler checks: `python3 -m unittest discover -s language-packs -p test_wiktextract.py -v`. Native tokenization qualification uses synthetic signed fixtures from `make_lookup_fixture.py`, separately proving Chinese/Japanese words within unspaced sentences, Korean/Arabic lookup, partial-word rejection, signature verification and install/remove behavior. These fixture assertions do not certify the upstream dictionary.

Primary source structure: https://github.com/tatuylonen/wiktextract#translations . Provenance/licensing: https://kaikki.org/dictionary/ and https://en.wiktionary.org/wiki/Wiktionary:Copyrights .

## Current context-pack research

The catalog/export descriptions above record the initial qualification. Current catalogs and native pair exports use schema 4. Every known source sense remains available to ambiguity checks even if it has no eligible target mapping. Contractions and phrases composed entirely of attested grammatical words remain native. See `docs/VERIFICATION.md` for current hashes, coverage and rejected experiments.

`build_context_examples.py` scans the pinned selected source for ordinary usage examples with explicit source and translation focus spans. It excludes quoted works/references, retains explicit readable romanization spans, and creates a native-portable SQLite FTS4 index. Schema `vipi-context-example-research-2` retains independent source/target code-point offsets and the original entry/sense/example usage evidence. These fields do not infer missing grammatical conditions. Native source and target positions may differ; example romanization must not be attached to an unrelated inflection. CJK bigrams assist retrieval without claiming word segmentation.

Build on OZZZ-OS under storage admission. The complete enriched research index is about 73 MiB for 18 direct English directions, not all 90 pairs. It is not a signed native vocabulary pack and exceeds that installer's current 64 MiB per-file bound. No production schema/trust change is implied. `qa/immersion/context_index_queries.py` creates portability checks; `context_retrieval_pilot.py` measures source-context retrieval on captured messages. Neither is a linguistic acceptance test. The latter's ranking has observed sense/person errors and is not integrated.

`sources/cygnet-20260512.json` pins a second research source, [Cygnet](https://github.com/omwn/cygnet/releases/tag/2026.05.12), including its separate provenance database. `fetch_cygnet.py` enforces release asset hashes, compressed/decompressed sizes, gzip integrity and SQLite integrity. Its measured acquisition bound is 991,307,668 data bytes plus a small receipt allowance. `qa/immersion/cygnet_coverage.py` measures ten-language concept links while retaining accent distinctions and grammatical exclusions. A source concept link does not prove that its synonyms are interchangeable in a new sentence. Korean coverage and several languages' native contexts are sparse. Source pronunciations are not automatically readable transliteration. Per-resource licenses and per-row attribution must be reviewed/preserved before distribution; do not apply the Cygnet code license to its mixed-source data.

## Incremental mapping authoring

`mapping_catalog.py` maintains the build-time SQLite authoring ledger, separate from downloadable client indexes. Import checkpoints and records commit in one transaction. Repeated input deduplicates; interrupted input resumes; source generations prevent an old resumed import from replacing a newer correction. Stable logical IDs retain immutable content revisions, source evidence, review history and a monotonic change sequence. Modifying an entry invalidates its previous content-specific review. Quarantine removes it from subsequent reviewed exports without discarding its history.

The ledger started with 112,304 attested context records. `authored_everyday.py` adds 370 project-authored candidates across all 90 directions, with explicit meanings, exact lexical spans and Roman readings for non-Roman targets. These are development seeds, not independent acceptance data. The four initial beverage/food concepts and book/route examples are deliberately bounded; this count must not be advertised as broad everyday coverage. New JSONL batches do not require rescanning dictionaries or rebuilding accepted history.

Run on OZZZ-OS with the applicable storage admission budget:

```sh
python3 language-packs/mapping_catalog.py import-index --catalog artifacts/mapping-catalog-001/catalog.sqlite --input artifacts/context-index-003 --batch-size 1000
python3 language-packs/authored_everyday.py --output artifacts/authored-everyday-NEW/records.jsonl
python3 language-packs/mapping_catalog.py import-records --catalog artifacts/mapping-catalog-001/catalog.sqlite --input artifacts/authored-everyday-NEW/records.jsonl --batch-size 100
python3 language-packs/mapping_catalog.py status --catalog artifacts/mapping-catalog-001/catalog.sqlite
```

Use `--max-batches` to bound an ingestion run. Review reports bind the exact record SHA, reviewer, content-addressed evidence and meaning/usage/grammar/provenance/reading checks. Explicit author assessments are allowed and labelled as such; an author cannot label their assessment independent. Full assessment evidence accompanies exports. Generation, a test pass or an FTS score alone supplies no review. `export-reviewed` emits an internal manifest with `release_ready:false`; independent pair-level quality and signed native-pack installation remain separate. This allows Codex-authored work to progress without pretending another provider or person reviewed it.

`context_patterns.py` validates optional finite source patterns: literals, explicitly enumerated slots and exactly one lexical focus. Slots never supply target text. Book examples enumerate supported subjects and possessors outside the replacement. Singular/plural focuses have separate mappings; unknown variants, conflicting meanings and ambiguous focus positions are withheld. The Kotlin and Swift implementations are native and bounded. These exact-context components do not yet provide broad phrase generalization or connect the ledger to general chat.

## Whole-message and phrase observations

`qa/immersion/prepare_phrase_probe.py` freezes the development protocol; its expected target terms never enter translation. Android `TranslationPhraseDeviceTest` translates the whole message, focus and overlapping native-token windows with networking disabled. Its synthetic QA SQLite cache is keyed by direction, exact input and protocol/provider epoch, persists case checkpoints, and supports replay without translation calls. It is not a production private-message cache or qualified model-content-version invalidation.

`qa/immersion/review_phrase_probe.py` reports unique correspondences, overlapping phrase agreement and exact reference-surface matches separately. Surface differences may be acceptable variants or errors. Native word boundaries, lexical scope and readings matter: Arabic `حساب` translated as `an account` imports an article into a nominal focus; Korean particles can prevent a bare dictionary noun from matching a native token. Same-provider agreement can repeat a wrong meaning. The physical Apple counterpart retains separate output and observed network state; it must actually run before Apple parity is claimed.

## Conversation-driven expansion

`authored_conversation.py` adds 20 common concepts in 1,782 exact contexts across all 90 directions. Counts do not multiply into distinct vocabulary size. Arabic possessive-family examples are withheld where a valid lexical surface cannot be separated safely. Every record has exact spans and readable target transliteration where required. `assess_authored_conversation.py` is bound to one inspected batch hash and actual native evidence: 1,764 records have an explicit author assessment, while 18 Chinese-source question/problem examples remain quarantined. It is not a generic automatic approval mechanism or independent linguistic review.

`qa/immersion/conversation_corpus.py` indexes pinned Tatoeba detailed exports, direct links, tags and transcriptions. All-link components and normalized duplicates determine an 85/15 development/reserved partition; known catalog contexts force their components into development. Transitive links group partitions only and never become translation evidence. The detailed tag export is **tag ID, sentence ID, contributor, timestamp**; the publisher's SQL is retained beside the acquisition receipt. Use corrected `conversation-corpus-002`, not the superseded revision-001 tag index.

`expand_conversation_contexts.py` extracts unique lexical focuses from direct development links, retains contributor/source/license attribution, and excludes editorial/error tags. Native ICU boundaries and transliteration checks are eligibility filters, not proof of meaning. Revision 002 selected 20,296 context candidates from 359,768 eligible links. These remain unreviewed. No reserved sentences are promoted by this tool.

`conversation_priority.py` measures source-surface recognition on development text; it does not measure correct substitutions. Its NUS SMS split hashes contributor IDs across languages, always assigns unknown contributors to development, removes reserved texts duplicated in development, and deduplicates reserved texts. The resulting 8,446 reserved messages are contributor-separated, not proven participant- or conversation-separated. Corpus metadata/phone numbers are not exported into reports or app packs. `grammar_coverage.py` measures lemma/morphology/dependency patterns in pinned Universal Dependencies **training** files. Grammar and frequency reports prioritize authoring; they are not runtime data.

Sources remain separate: [Tatoeba](https://tatoeba.org/en/downloads) text uses CC BY 2.0 FR except its explicitly marked CC0 subset; audio is not acquired. [NUS SMS](https://github.com/kite1988/nus-sms-corpus) is the authors' public-domain SMS release and is retained only for research. UD English EWT and French Rhapsodie use CC BY-SA 4.0; other UD treebanks need their own license checks. These datasets complement one another and do not establish representative coverage for all demographics or all ten languages.

The second authored batch, `authored_conversation_expansion.py`, adds 1,800 contexts for 20 everyday meanings. Its content-bound assessment is separate from the original batch. Current reviewed export contains 3,567 records, including three finite book patterns; 18 ambiguous Chinese question/problem records remain quarantined. Forty new meanings are not 3,567 distinct vocabulary words.

## Signed reviewed context packs

`export_reviewed_contexts.py` compiles the reviewed export into schema-5 SQLite pair files. Each retains exact provenance and assessments, UTF-16 target offsets, finite source patterns and a B-tree index of explicitly enumerated source variants. The compiler rejects changed/unreviewed records, absent required reading assessments, ambiguous patterns and variant/shortlist overflow. It does not rank a similar sentence as equivalent or interpolate a target using a user's pronouns. Whole-message translation still corroborates the lexical target.

Both native `VocabularyPackStore` implementations use an explicit `reviewedContext`/`REVIEWED_CONTEXT` kind, separate files and rollback receipts, and the existing signature/hash/integrity controls. A generic dictionary store rejects a context pack. Only matched context patterns create message-bound lexical scopes; target particle/article boundaries derive from the attested target sentence using the native tokenizer. Lookup returns no result for an unknown sentence. This path is not yet connected to friend chat or production download UI.

The first development build contains 90 pairs and 3,567 reviewed mappings in 17,936,384 bytes; its compressed qualification archive is 1,160,225 bytes. Its ephemeral signing key is never trusted by production clients. Real native qualification covers the two retained translation batches: 3,564/3,582 cases have reviewed mappings, with 2,996 Android and 3,250 iPad cases producing immersion. The other 18 cases are quarantined. These are component checks on authored inputs, not majority-conversation acceptance. See `docs/CONVERSATION_COVERAGE.md` for the separate real-message evaluation.

```sh
python3 language-packs/export_reviewed_contexts.py --input artifacts/conversation-assessment-002/export --output artifacts/reviewed-contexts-NEW --revision 1 --key-id reviewed-context-qualification-NEW
```

The compiler currently exposes only qualification signing. Production release signing and release trust remain separate gates; generating an artifact is not evidence of release readiness.
