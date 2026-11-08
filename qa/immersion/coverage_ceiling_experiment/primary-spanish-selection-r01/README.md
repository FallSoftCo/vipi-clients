# Spanish lexical evidence, research revision 1

These 210 retained per-word JSONL files are English Wiktionary Spanish entries extracted by Kaikki/Wiktextract. They occupy 1,809,637 bytes. Each original URL, fetch time, byte count and SHA-256 is in `manifest.json`; each selected sense in the generated lexicon links to its Wiktionary page and content-addressed record. The raw extracts and derived lexical data retain CC BY-SA 4.0 attribution to the English Wiktionary contributors. See https://creativecommons.org/licenses/by-sa/4.0/ and https://kaikki.org/dictionary/Spanish/.

`targets-draft.json` preserves the authored target choices and exclusions made before the paired held-out sample was opened. The draft is an input, not independently validated language data. No model or provider is needed to reproduce the frozen files:

```sh
python3 prepare_spanish_transfer_r01.py --output /disk-backed/new-output-directory
```

Run that command from the parent directory, or pass the script's full path. It verifies retained inputs, rebuilds the target lexicon/question rules/control, and compares them with the frozen original SHA-256 values. Existing outputs are never overwritten. This does not rerun semantic review or claim production/native qualification.
