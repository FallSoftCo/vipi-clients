#!/usr/bin/env python3
"""Preserve source grammar using the pinned dictionaries' native POS evidence.

A spelling with a grammatical use is excluded conservatively, even if it also
has a lexical sense. This is an abstention list, never a translation mapping.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import time

from build_wiktextract import LANGUAGES, EXCLUDED, canonical, clean, form_ok, digest_file
from context_hints import lookup_key

CLOSED_CLASS = {"article", "det", "pron", "prep", "postp", "conj", "particle", "aux"}
GRAMMATICAL_TAGS = {"auxiliary", "copulative", "copula"}


def grammatical(entry):
    if entry.get("pos") in CLOSED_CLASS:
        return "part_of_speech:" + entry["pos"]
    tags = set(entry.get("tags", []))
    for sense in entry.get("senses", []):
        tags.update(sense.get("tags", []))
    matches = sorted(tags & GRAMMATICAL_TAGS)
    return "sense_tag:" + ",".join(matches) if matches else None


def collect(entry, line, terms):
    language = entry.get("lang_code")
    if language not in LANGUAGES or set(entry.get("tags", [])) & EXCLUDED:
        return
    reason = grammatical(entry)
    if reason is None:
        return
    forms = [entry.get("word", "")]
    forms.extend(item.get("form", "") for item in entry.get("forms", [])
                 if isinstance(item, dict) and not set(item.get("tags", [])) & (EXCLUDED | {"romanization", "transliteration"}))
    for form in forms:
        form = clean(form)
        if form_ok(form):
            key = lookup_key(form, language)
            terms[language].setdefault(key, {"line": line, "headword": entry.get("word"), "reason": reason})


def main(args):
    if args.output.exists():
        raise ValueError("Preserve previous derivations")
    started = time.monotonic()
    terms = {language: {} for language in LANGUAGES}
    counts = Counter()
    with gzip.open(args.source, "rb") as source:
        for line, raw in enumerate(source, 1):
            entry = json.loads(raw)
            counts[entry.get("pos", "unknown")] += 1
            collect(entry, line, terms)
            if line % 1_000_000 == 0:
                print(canonical({"entries_scanned": line, "seconds": time.monotonic() - started}), flush=True)
    document = {"schema": "vipi-native-grammar-guard-1", "quality": "candidate_abstention_data",
                "source_sha256": digest_file(args.source), "compiler_sha256": digest_file(Path(__file__)),
                "license": "CC-BY-SA-4.0", "attribution": "Wiktionary contributors; extraction by Tatu Ylonen/wiktextract via Kaikki.org.",
                "evidence": "native_headword_and_inflections_with_closed_class_or_auxiliary_tag",
                "terms": terms, "part_of_speech_counts": dict(counts), "seconds": time.monotonic() - started}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical(document) + "\n")
    print(canonical({"output": str(args.output), "bytes": args.output.stat().st_size,
                     "sha256": digest_file(args.output), "counts": {k: len(v) for k, v in terms.items()}, "seconds": document["seconds"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    main(parser.parse_args())
