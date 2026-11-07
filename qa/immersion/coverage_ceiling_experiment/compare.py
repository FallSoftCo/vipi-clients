#!/usr/bin/env python3
"""Compare production A, deliberately relaxed lexical B, and whole-flip C.

Evaluation only. B bypasses contextual sense gates to measure their tradeoff;
it is expected to introduce meaning errors. C is a UX possibility, not a claim
that a whole translation teaches vocabulary or is necessarily correct.
"""
import argparse
import collections
import json
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from noun_boundary_experiment import Dictionary, digest, mixed, tokens, u16

CONTENT_POS = {"noun", "adj", "adv", "verb", "phrase"}


def windows(text):
    words = tokens(text)
    result = []
    for index, word in enumerate(words):
        for width in range(1, min(4, len(words) - index) + 1):
            last = words[index + width - 1]
            original = text[word["start"]:last["end"]]
            if width > 1 and not re.fullmatch(r"[^\W_]+(?:['’][^\W_]+)?(?:[ \t]+[^\W_]+(?:['’][^\W_]+)?)+", original):
                continue
            result.append({"text": original, "key": " ".join(original.lower().split()),
                           "start": word["start"], "end": last["end"],
                           "range": [word["rangeUTF16"][0], last["rangeUTF16"][1]], "words": width})
    return result


def complete_forms(dictionary, text):
    output = []
    diagnostics = collections.Counter()
    for window in windows(text):
        eligible = []
        for form in dictionary.analyses(window["key"]):
            if form["pos"] not in CONTENT_POS or not form["target_safe"]:
                diagnostics["noncontent_or_unsafe_analysis"] += 1
                continue
            if form["grammar_guard"] or form["guard_reason"] == "grammar":
                diagnostics["grammatical_analysis"] += 1
                continue
            if form["mode"] not in (1, 2, 4, 5) or form["start"] != 0 or form["end"] != u16(form["surface"]):
                diagnostics["incomplete_or_unsupplied_form"] += 1
                continue
            # Lower-case common forms with only sentence-initial capitalization.
            # Proper names, acronyms, and arbitrary SMS capitals are not assumed
            # to denote the common same-spelled lexeme.
            actual = window["text"]
            written = form["surface"]
            if actual != written:
                initial = not text[:window["start"]].strip() or bool(re.search(r"[.!?。！？]\s*$", text[:window["start"]]))
                if not (initial and actual[:1].isupper() and actual[1:] == written[1:] and written[:1].islower()):
                    diagnostics["written_case_differs"] += 1
                    continue
            meanings = {term["sense"] for term in form["terms"] if term["eligible"]}
            if meanings:
                eligible.append((form, meanings))
        if eligible:
            output.append((window, eligible))
    return output, dict(diagnostics)


def overlaps(a, b, side="source"):
    return a[side + "StartUTF16"] < b[side + "EndUTF16"] and b[side + "StartUTF16"] < a[side + "EndUTF16"]


def relaxed(original, translation, source_db, target_db, baseline):
    left, left_diag = complete_forms(source_db, original)
    right, right_diag = complete_forms(target_db, translation)
    candidates, rejected = [], []
    for word, forms in left:
        claims = {}
        for other, targets in right:
            if word["key"] == other["key"]:
                continue
            pairs = []
            for a, senses_a in forms:
                for b, senses_b in targets:
                    if a["pos"] != b["pos"] or a["number"] != b["number"]:
                        continue
                    shared = senses_a & senses_b
                    if shared:
                        pairs.append({"source_lexeme": a["lexeme"], "target_lexeme": b["lexeme"],
                                      "pos": a["pos"], "shared_senses": sorted(shared)})
            if pairs:
                claims[tuple(other["range"])] = (other, pairs)
        if len(claims) != 1:
            if claims:
                rejected.append({"original": word["text"], "source_range": word["range"],
                                 "reason": "multiple_target_positions", "target_ranges": list(claims)})
            continue
        (start, end), (other, pairs) = next(iter(claims.items()))
        candidates.append({"sourceStartUTF16": word["range"][0], "sourceEndUTF16": word["range"][1],
                           "original": word["text"], "translated": other["text"],
                           "targetStartUTF16": start, "targetEndUTF16": end, "reading": None,
                           "origin": "eval_only_relaxed_complete_dictionary", "evidence": pairs})
    # Keep A intact; try larger complete phrases first, then source order.
    selected = [dict(span, origin="production_A") for span in baseline]
    for candidate in sorted(candidates, key=lambda s: (-(s["sourceEndUTF16"] - s["sourceStartUTF16"]), s["sourceStartUTF16"])):
        if any(overlaps(candidate, span) or
               (span.get("targetCoordinateBasis") != "reference_unit" and overlaps(candidate, span, "target")) for span in selected):
            continue
        rivals = [c for c in candidates if c is not candidate and overlaps(c, candidate, "target") and not overlaps(c, candidate)]
        if rivals:
            rejected.append({"original": candidate["original"], "source_range": [candidate["sourceStartUTF16"], candidate["sourceEndUTF16"]],
                             "reason": "competing_nonoverlapping_source_claim", "rivals": [r["original"] for r in rivals]})
            continue
        selected.append(candidate)
    selected.sort(key=lambda s: s["sourceStartUTF16"])
    return {"spans": selected, "visible": mixed(original, selected), "candidate_count": len(candidates),
            "rejections": rejected, "source_analysis_diagnostics": left_diag, "target_analysis_diagnostics": right_diag}


def native_rows(capture):
    return capture.get("cases", capture.get("results", []))


def full_translation(row):
    choices = []
    for density in row.get("densities", []):
        for call in density.get("provider_calls", []):
            if isinstance(call.get("translation"), str) and call["translation"].strip():
                choices.append((call["translation"], call.get("identifiers_preserved"), "production_provider_call"))
    probe = row.get("evaluation_full_translation_probe")
    if isinstance(probe, dict):
        text = probe.get("translation", probe.get("text"))
        if isinstance(text, str) and text.strip():
            choices.append((text, probe.get("identifiers_preserved"), "evaluation_only_provider_call"))
    if not choices and isinstance(row.get("translation"), str):
        choices.append((row["translation"], row.get("identifier_guard"), "retained_capture"))
    if not choices:
        for density in row.get("densities", []):
            if isinstance(density.get("complete_translation"), str) and density["complete_translation"].strip():
                choices.append((density["complete_translation"], None, "complete_translation_without_provider_trace"))
    if not choices:
        return None, None, "missing", False
    return *choices[0], len({value[0] for value in choices}) > 1


def depth(spans, ranges):
    if not ranges:
        return 0
    covered = sum(any(s["sourceStartUTF16"] <= a and s["sourceEndUTF16"] >= b for s in spans) for a, b in ranges)
    return covered / len(ranges)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--dictionary-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pair", help="Optional source-target subset; preserves original protocol hash")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite retained evidence")
    protocol = json.loads(args.protocol.read_text())
    capture = json.loads(args.capture.read_text())
    if capture.get("input_sha256") != digest(args.protocol):
        parser.error("capture input identity mismatch")
    if args.pair:
        protocol["cases"] = [case for case in protocol["cases"] if case["source"] + "-" + case["target"] == args.pair]
        if not protocol["cases"]:
            parser.error("pair has no protocol cases")
    rows = {(row["id"], row["source"], row["target"]): row for row in native_rows(capture)}
    languages = {case[side] for case in protocol["cases"] for side in ("source", "target")}
    dictionaries = {language: Dictionary(args.dictionary_dir / f"d-{language}.sqlite") for language in languages}
    results = []
    for case in protocol["cases"]:
        row = rows.get((case["id"], case["source"], case["target"]))
        if row is None:
            results.append({**case, "status": "native_not_captured"})
            continue
        original = row.get("original", case["text"])
        if original != case["text"]:
            parser.error("native source changed")
        dense = next((r for r in row.get("densities", []) if r["density"] == 1), None)
        if dense is None:
            results.append({**case, "status": "native_max_density_missing"})
            continue
        ranges = row.get("native_source_word_ranges", row.get("source_word_ranges"))
        if ranges is None:
            parser.error("native source word ranges missing")
        baseline = [dict(span, targetCoordinateBasis="reference_unit" if dense.get("path") == "SOURCE_REFERENCE_PARTIAL" else "full_translation")
                    for span in dense.get("spans", [])]
        translation, identifiers, provenance, differed = full_translation(row)
        result = {**case, "original": original, "translation": translation, "translation_provenance": provenance,
                  "provider_outputs_differ": differed, "identifiers_preserved": identifiers,
                  "native_word_ranges": ranges, "native_outcome": dense.get("status"), "native_path": dense.get("path"),
                  "A": {"spans": baseline, "visible": dense.get("visible", dense.get("mixed", original)), "depth": depth(baseline, ranges)},
                  "semantic_assessment": "pending_author_review", "status": "compared"}
        if not translation or identifiers is not True:
            result["B"] = {"status": "full_translation_missing_or_identifier_unproved", "spans": baseline,
                           "visible": result["A"]["visible"], "depth": result["A"]["depth"]}
            result["C"] = {"status": "full_translation_missing_or_identifier_unproved", "visible": original, "changed": False}
        else:
            began = time.perf_counter()
            result["B"] = relaxed(original, translation, dictionaries[case["source"]], dictionaries[case["target"]], baseline)
            result["B"].update(status="evaluated_only", depth=depth(result["B"]["spans"], ranges), python_ms=(time.perf_counter()-began)*1000)
            changed = [t["key"] for t in tokens(original)] != [t["key"] for t in tokens(translation)]
            result["C"] = {"status": "whole_local_translation_flip_candidate", "visible": translation,
                           "changed": changed, "semantic_depth": "unmeasured; full message exposure is not vocabulary mastery"}
        # A confirmed source-only whole reference takes precedence over the
        # separately requested evaluation MT probe, exactly as the proposal says.
        reference = dense.get("complete_translation")
        if dense.get("path") == "LOOKUP_REFERENCE" and isinstance(reference, str) and reference.strip():
            result["C"] = {"status": "whole_catalog_reference_flip_candidate", "visible": reference,
                           "changed": [t["key"] for t in tokens(original)] != [t["key"] for t in tokens(reference)],
                           "semantic_depth": "unmeasured; full message exposure is not vocabulary mastery"}
        results.append(result)
    summary = {}
    for pair in sorted({(r["source"], r["target"]) for r in results}):
        group = [r for r in results if (r["source"], r["target"]) == pair]
        done = [r for r in group if r["status"] == "compared"]
        item = {"requested": len(group), "captured": len(done), "semantic_review_complete": False}
        if done:
            for arm in ("A", "B"):
                item[arm] = {"messages_with_span": sum(bool(r[arm]["spans"]) for r in done),
                             "spans": sum(len(r[arm]["spans"]) for r in done),
                             "mean_native_word_depth": statistics.mean(r[arm]["depth"] for r in done)}
            item["C"] = {"changed_whole_translations": sum(r["C"]["changed"] for r in done)}
        summary["-".join(pair)] = item
    report = {"schema": "vipi-coverage-ceiling-comparison-1", "release_ready": False, "relaxed_arm_production": False,
              "capture_sha256": digest(args.capture), "input_sha256": digest(args.protocol), "runner_sha256": digest(__file__),
              "dictionary_hashes": {lang: digest(args.dictionary_dir / f"d-{lang}.sqlite") for lang in languages},
              "capture_complete": capture.get("complete", False), "summary": summary, "results": results}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
