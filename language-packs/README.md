# Local vocabulary data

First source: FreeDict + WikDict English–Spanish 2025.11.23, 64,258 upstream headwords. Its own TEI header declares **CC BY-SA 3.0** and credits Karl Bartel, Wiktionary contributors and DBnary. The source archive is pinned by SHA-512 and size. This does not imply the same license applies to every FreeDict dictionary.

`build_pack.py` reads exact bounded archive members, verifies the declared license, retains attribution/license/header, removes grammatical function-word and proper-name entries by part of speech, normalizes source forms and creates SQLite mappings. It keeps all viable senses; the native context filter must abstain when translation corroborates more than one. It does not infer morphology, certify translations, or produce a frequency-ranked learning curriculum.

The immutable SQLite file and canonical manifest are covered by SHA-256 and a detached P-256/SHA-256 signature. Native installers must pin a release public key, verify the original manifest bytes and content hash, enforce bounds/schema/revision, and swap files atomically. The development signing key is private and must not be trusted by production apps. The included public key is for build verification; downloading a key alongside a pack is not a trust model.

The derived pack remains CC BY-SA 3.0. Distribute attribution, full license, original pinned source link, transformation source and a description of changes with public releases. Current outputs are engineering fixtures, not published or quality-qualified language packs. Do not use dictionary headword count as a language-learning efficacy claim.

Primary sources: https://freedict.org/documentation/ and https://freedict.org/freedict-database.json . Every added language needs separate provenance/license and contextual quality review.
