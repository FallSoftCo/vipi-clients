These are the pinned Apache OpenNLP 2.5.10 tools, SLF4J API 2.0.18 and English UD-EWT 1.3 sentence, token and POS models. Model filenames retain their publisher's `2.5.4` suffix. `manifest.json` records the exact binary, Unicode table and license/notice hashes. Run `scripts/check-source-context-assets.py` from the repository root to verify them without network access.

Publisher references: [Apache OpenNLP](https://opennlp.apache.org/), [OpenNLP model releases](https://opennlp.apache.org/models.html), and [SLF4J](https://www.slf4j.org/). The retained model README describes the model naming and training corpus. These files are bundled dependencies; the app does not download them at runtime.

The app bundles the publisher licenses and notices under `source-context/licenses/`. Keep those files with the models. POS tagging does not establish entity recognition or correct word sense; no NER model is included here.
