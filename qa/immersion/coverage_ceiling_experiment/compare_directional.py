#!/usr/bin/env python3
"""QA-only directional comparison using captured native word boundaries.

Extends the relaxed evaluation arm to Japanese without pretending whitespace
splitting is Japanese segmentation. Added Japanese spans require an unambiguous
attested reading for that precise surface. No production matcher is changed.
"""
import argparse
import collections
import json
from pathlib import Path
import re
import statistics
import unicodedata

import compare as base


def windows(text, ranges):
    raw = text.encode("utf-16-le")
    words = []
    last_end = 0
    for start, end in ranges:
        if not (0 <= last_end <= start < end <= len(raw)//2):
            raise ValueError("invalid native word geometry")
        surface = raw[start*2:end*2].decode("utf-16-le")
        prefix = raw[:start*2].decode("utf-16-le")
        suffix = raw[:end*2].decode("utf-16-le")
        if any(c.isalpha() or c.isdigit() for c in surface):
            words.append({"text": surface, "start": len(prefix), "end": len(suffix), "range": [start, end]})
        last_end = end
    result = []
    for i, word in enumerate(words):
        for width in range(1, min(4, len(words)-i)+1):
            group = words[i:i+width]
            if any(text[a["end"]:b["start"]].strip() for a, b in zip(group, group[1:])):
                continue
            last = group[-1]
            actual = text[word["start"]:last["end"]]
            result.append({"text": actual, "key": " ".join(actual.lower().split()),
                           "start": word["start"], "end": last["end"],
                           "range": [word["range"][0], last["range"][1]], "words": width})
    return result


def roman(reading):
    return bool(reading.strip()) and all(not c.isalpha() or "LATIN" in unicodedata.name(c, "") for c in reading)


def reading_for(span, target):
    readings = set()
    key = " ".join(span["translated"].lower().split())
    for evidence in span["evidence"]:
        lexeme = evidence["target_lexeme"]
        for sense in evidence["shared_senses"]:
            specific = target.db.execute("SELECT reading FROM surface_readings WHERE normalized=? AND lexeme=? AND sense=?",
                                         (key, lexeme, sense)).fetchall()
            readings.update(r[0] for r in specific if roman(r[0]))
            # A canonical reading is not valid for an arbitrary inflected form.
            canonical = target.db.execute("SELECT 1 FROM surfaces WHERE normalized=? AND lexeme=? AND surface=? AND mode IN (1,2)",
                                          (key, lexeme, span["translated"])).fetchone()
            if canonical:
                rows = target.db.execute("SELECT reading FROM terms WHERE lexeme=? AND sense=? AND eligible=1", (lexeme, sense))
                readings.update(r[0] for r in rows if roman(r[0]))
    return next(iter(readings)) if len(readings) == 1 else None, sorted(readings)


def provider_ranges(row, translation):
    calls = [c for density in row["densities"] for c in density.get("provider_calls", [])]
    if isinstance(row.get("evaluation_full_translation_probe"), dict):
        calls.append(row["evaluation_full_translation_probe"])
    found = [c["native_target_word_ranges"] for c in calls
             if c.get("translation") == translation and c.get("native_target_word_ranges") is not None]
    if not found or any(r != found[0] for r in found[1:]):
        return None
    return found[0]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--protocol", type=Path, required=True)
    p.add_argument("--capture", type=Path, required=True)
    p.add_argument("--dictionary-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        p.error("refusing to overwrite evidence")
    protocol, capture = json.loads(args.protocol.read_text()), json.loads(args.capture.read_text())
    assert capture["input_sha256"] == base.digest(args.protocol)
    key = lambda r: (r["id"], r["source"], r["target"])
    native = {key(r): r for r in base.native_rows(capture)}
    languages = {c[side] for c in protocol["cases"] for side in ("source", "target")}
    dictionaries = {lang: base.Dictionary(args.dictionary_dir / f"d-{lang}.sqlite") for lang in languages}
    results = []
    for case in protocol["cases"]:
        row = native.get(key(case))
        if row is None:
            results.append({**case, "status": "native_missing"})
            continue
        assert row["original"] == case["text"]
        dense = next((d for d in row["densities"] if d["density"] == 1), None)
        if dense is None:
            results.append({**case, "status": "native_density_incomplete"})
            continue
        original = row["original"]
        source_ranges = row["native_source_word_ranges"]
        # Validate surrogate boundaries even if A has no spans.
        windows(original, source_ranges)
        a = [dict(s, origin="production_A", targetCoordinateBasis="reference_unit"
                  if dense.get("path") == "SOURCE_REFERENCE_PARTIAL" else "full_translation")
             for s in dense.get("spans", [])]
        translation, identifiers, provenance, differed = base.full_translation(row)
        result = {**case, "original": original, "translation": translation, "translation_provenance": provenance,
                  "provider_outputs_differ": differed, "identifiers_preserved": identifiers,
                  "native_source_word_ranges": source_ranges, "native_path": dense.get("path"),
                  "native_outcome": dense.get("status"), "semantic_assessment": "pending_author_review", "status": "compared",
                  "A": {"spans": a, "visible": dense.get("visible", original), "depth": base.depth(a, source_ranges),
                        "missing_or_nonroman_readings": [s for s in a if case["target"] == "ja" and not roman(s.get("reading") or "")]}}
        target_ranges = provider_ranges(row, translation)
        if translation and identifiers is True and target_ranges is not None and translation != original:
            windows(translation, target_ranges)
            saved = base.windows
            try:
                base.windows = lambda text: windows(text, source_ranges if text == original else target_ranges)
                b = base.relaxed(original, translation, dictionaries[case["source"]], dictionaries[case["target"]], a)
            finally:
                base.windows = saved
            if case["target"] == "ja":
                accepted = []
                for span in b["spans"]:
                    if span["origin"] == "production_A":
                        accepted.append(span)
                        continue
                    reading, candidates = reading_for(span, dictionaries["ja"])
                    if reading is None:
                        b["rejections"].append({"span": span, "reason": "missing_or_ambiguous_surface_reading", "reading_candidates": candidates})
                    else:
                        accepted.append({**span, "reading": reading})
                b["spans"] = accepted
            b.update(visible=base.mixed(original, b["spans"]), depth=base.depth(b["spans"], source_ranges), status="evaluation_only_native_windows")
        else:
            b = {"spans": a, "visible": result["A"]["visible"], "depth": result["A"]["depth"],
                 "status": "unavailable_or_unchanged_full_translation_or_native_ranges"}
        result["B"] = b
        result["C"] = {"visible": translation, "changed": bool(translation and translation != original),
                       "identifiers_preserved": identifiers,
                       "reading_qualification": "full_sentence_reading_not_captured" if case["target"] == "ja" else "Latin_target"}
        results.append(result)
    summary = {}
    for pair in sorted({(r["source"],r["target"]) for r in results}):
        rs = [r for r in results if (r["source"],r["target"]) == pair and r["status"] == "compared"]
        summary["-".join(pair)] = {"captured": len(rs), **{arm: {"messages_with_spans": sum(bool(r[arm]["spans"]) for r in rs),
              "spans": sum(len(r[arm]["spans"]) for r in rs), "mean_native_word_depth": statistics.mean(r[arm]["depth"] for r in rs) if rs else None}
              for arm in ("A", "B")}, "A_reading_gaps": sum(len(r["A"]["missing_or_nonroman_readings"]) for r in rs)}
    value = {"schema": "vipi-directional-native-boundary-comparison-1", "production": False,
             "input_sha256": base.digest(args.protocol), "capture_sha256": base.digest(args.capture), "capture_complete": capture.get("complete", False),
             "runner_sha256": base.digest(__file__), "base_runner_sha256": base.digest(base.__file__),
             "dictionary_hashes": {lang:base.digest(args.dictionary_dir/f"d-{lang}.sqlite") for lang in languages},
             "limitations": "B is a relaxed QA arm. Native boundaries and nonempty roman readings are not semantic acceptance. Japanese C has no full-sentence reading proof in this harness.",
             "summary": summary, "results": results}
    args.output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(summary,indent=2))


if __name__ == "__main__":
    main()
