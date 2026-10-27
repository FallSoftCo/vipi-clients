# Bulk lexical context pipeline

This is the 2026-10-27 data expansion for consumer Vipi. The default app bundle
is still 022. Broad lexical shards have native QA evidence; the newly mined
contexts are **candidate evidence, not accepted runtime mappings**.

## Completed build

`artifacts/lexical-contexts-001/contexts.sqlite` contains:

- 5,029,353 development sentences scanned across eleven languages, including Swahili.
- 4,850,485 sentences with lexical evidence and 20,643,191 indexed form occurrences.
- 7,446,251 candidate alignments from 2,925,016 directly linked sentence pairs.
- 2,144,896 sentence pairs with at least one alignment and 67,918 candidate sense IDs.
- 4,069 editorially flagged sentences excluded from scanning.

The database is **1,629,253,632 bytes**, SHA-256
`c335b3d9b51adff2b4ebfc49d0909f58a3217ed708b4754b3d519f4b629a5055`.
The complete scan and join took 893.22 seconds on OZZZ-OS. The receipt is
`artifacts/lexical-contexts-001/receipt.json`.

Counts are not unique verified meanings or demonstrated conversation coverage.
Several dictionary sense IDs can describe the same written source/target pair.
The independent SMS, dialogue and Swahili captures do not enter this build.
Only the existing development partition is used; reserved sentence text is
excluded. Transitive graph links protect the partition but never supply new
translation pairs.

## Sources and Swahili

The main input is the pinned Tatoeba corpus 002, SHA
`a07e1d33c67a876df78c2221ce568e67c5aea773fae8c5d814458838095b28a5`.
Tatoeba publishes these sentence exports under
[CC BY 2.0 FR](https://tatoeba.org/en/downloads). Sentence IDs, individual
contributors and direct links remain available for attribution and inspection.
Dictionary evidence comes from the separately pinned Wiktionary inventory and
keeps its CC BY-SA 4.0 attribution.

`extend_swahili_corpus.py` adds a separate development supplement using the
same weekly translation-graph export. The Swahili sentence export is 109,352
compressed bytes, SHA
`6f0b77bd207427b21cee90b248d9ee3d0df4e8438de50543eee8024bf23e2d19`.
The supplement retains 3,899 Swahili sentences and 4,194 direct links to the
other languages. Duplicate Swahili groups touching reserved components are
excluded. Its duplicate-neighbor audit found no partially retained groups.
No reserved foreign sentence text is imported into the supplement.

The resulting context build finds lexical evidence in 3,421 of those Swahili
sentences. It retains 7,890 English–Swahili candidate sense alignments. These
are candidate availability figures, not a semantic accuracy score.

## Indexed representation

`qa/immersion/build_lexical_contexts.py` scans the complete retained dictionary
vocabulary rather than a short seed list. A build-time Aho–Corasick index finds
attested forms, and ICU checks the original word boundaries. Unicode
normalization retains explicit mappings to original UTF-16 offsets, including
combining marks and supplementary characters. Repeated occurrences and
competing lexical analyses cannot silently become unique alignments.

Each occurrence is stored once. Shared dictionary analyses live in `lexicon`,
source identities in `senses`, attributed text in `sentences`, and direct-pair
correspondences in `alignments`. This avoids repeating every possible sense at
every occurrence. Full-text search supports authoring and inspection.
This authoring database uses FTS5; it is **not a qualified Android/iOS download
format**. The separately tested native lexical shards use ordinary SQLite
indexes. A runtime context format and selector still need qualification.

The deterministic 16-row English–Spanish pilot review found useful written
word correspondences but also dictionary labels that were wrong or unproven
for the specific context. For example, a time duration can share a dictionary
link carrying a school-year label. Therefore these sense IDs must not be used
as automatically verified classifier labels. The review receipt is
`artifacts/lexical-contexts-pilot-003/sample-review-001.json`; it is an author
review, not independent or representative accuracy measurement.

## Reproduction and incremental updates

All substantial work runs on OZZZ-OS through storage admission. The build-time
environment uses system ICU and pinned `pyahocorasick==2.2.0`; this adds no
Python dependency to either app. Run from `/aosp/development/vipi`:

```sh
storage-build --peak-bytes 6442450944 -- \
  .venv-lexical-context/bin/python qa/immersion/build_lexical_contexts.py \
  --shards artifacts/lexical-shards-006 \
  --corpus artifacts/conversation-corpus-002/corpus.sqlite \
  --supplement artifacts/swahili-corpus-001/corpus.sqlite \
  --output artifacts/lexical-contexts-NEXT
```

Use a fresh output revision. Scanning the archived corpus directly is slower;
the completed build used a budgeted, hash-verified temporary disk copy on
OZZZ-OS. That working copy was retired after completion, while the original
consumer path, hashes and provenance remained intact. No build trees are placed
in RAM. The reserve remains 8 GiB plus other live reservations.

Dictionary compilers retain source hashes, compiler hashes and release IDs;
`--language` supports individual language builds from the pinned inventory.
New inputs can be rebuilt, compared against the existing replays and reviewed
without changing the current app bundle. No recurring model job was created.

`qa/immersion/lexical_delta.py` creates and applies **QA fixture** deltas with
base-file, patch-file and reconstructed-file hashes. The 006→007 fixture update
used 38,211,928 patch bytes for 1,586,442,240 reconstructed bytes. All eleven
files were reconstructed and verified on the Mac before physical iPad testing.
This is tested qualification transport; production manifests, signatures and
streaming installers remain a separate release requirement.

## Validation and corrections

Four targeted tests cover original UTF-16 geometry, Unicode expansions,
subword rejection, repeated/competing occurrences, reserved-data exclusion,
supplement handling, full-text retrieval and output-receipt binding.

The first completed full-build receipt accidentally hashed the supplemental
input because a loop variable shadowed the output path. The database itself
passed integrity checks and its row counts matched. The original compiler and
receipt remain in the artifact directory. The final receipt records the
correct database hash and a correction chain; the compiler is fixed and the
tiny end-to-end supplement test reproduces and prevents that error.

Superseded generated shard revisions were retired after checking hashes,
hard links and open consumers. Their catalogs, native reports and source
snapshots remain. See `artifacts/lexical-generated-retirement-001.json`.

The next acceptance step is contextual selection and native app integration.
Source inventory size, candidate retrieval, actual displayed spans, semantic
precision and physical-device UX remain separate measurements.
