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

This schema-2 research catalog is intentionally rejected by the current schema-1 native pack installer. It is not signed with a production key or published as a usable download. Context evaluation, approved pair export, native reading/provenance queries, signed release packaging and download/removal UI remain release gates. The source and transformed data use CC BY-SA 4.0; public distribution must include attribution, the full license and corresponding transformation source. The existing FreeDict pack retains its separate CC BY-SA 3.0 license.

Compiler checks: `python3 -m unittest discover -s language-packs -p test_wiktextract.py -v`. Native tokenization qualification uses synthetic signed fixtures from `make_lookup_fixture.py`, separately proving Chinese/Japanese words within unspaced sentences, Korean/Arabic lookup, partial-word rejection, signature verification and install/remove behavior. These fixture assertions do not certify the upstream dictionary.

Primary source structure: https://github.com/tatuylonen/wiktextract#translations . Provenance/licensing: https://kaikki.org/dictionary/ and https://en.wiktionary.org/wiki/Wiktionary:Copyrights .
