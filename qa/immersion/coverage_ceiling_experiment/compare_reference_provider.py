#!/usr/bin/env python3
"""QA-only cached chunk agreement with two actual full-reference providers."""
import argparse
import collections
import hashlib
import json
import math
import re
from pathlib import Path

from compare_direct_extension import aligned, ARMS, cut, key, mixed, select


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def letter_ranges(text):
    return [[len(text[:m.start()].encode("utf-16-le")) // 2,
             len(text[:m.end()].encode("utf-16-le")) // 2]
            for m in re.finditer(r"[^\W\d_]+(?:['’][^\W\d_]+)*", text)]


def protected_names(message):
    result = []
    for a, b in message["native_source_word_ranges"]:
        word = cut(message["text"], a, b)
        before = cut(message["text"], 0, a).rstrip().rstrip('"\'“”‘’')
        sentence_start = not before or before[-1] in ".!?"
        if word and word[0].isupper() and word != "I" and not sentence_start:
            result.append(key(word))
    return collections.Counter(result)


def protected(candidate, message):
    numbers = lambda text: collections.Counter(re.findall(r"\d+(?:[.,:/]\d+)*", text))
    if numbers(candidate["original"]) != numbers(candidate["translated"]):
        return "source_target_numeric_change"
    names = protected_names(message)
    source = collections.Counter(key(cut(candidate["original"], a, b))
                                 for a, b in letter_ranges(candidate["original"]))
    target = collections.Counter(key(cut(candidate["translated"], a, b))
                                 for a, b in letter_ranges(candidate["translated"]))
    if (source & names) != (target & names):
        return "protected_name_change_or_wrong_scope"
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    freeze = json.loads(args.freeze.read_text())
    values = {}
    for name, file in freeze["input_hashes"].items():
        assert sha(file["path"]) == file["sha256"]
        values[name] = json.loads(Path(file["path"]).read_text())
    protocol, chunks, slm = (values[k] for k in ("protocol", "chunks", "slm_reference"))
    assert chunks["complete"] and slm["complete"]
    calls = {r["id"]: r for r in chunks["requests"]}
    references = {r["id"]: r for r in slm["cases"]}
    messages = [r for r in protocol["messages"] if r["target"] == "sw"]
    assert len(messages) == len(references) == 80
    args.output_dir.mkdir(exist_ok=True)
    for provider in ("mlkit", "afrislm"):
        rows, boundary_differences = [], []
        for message in messages:
            full = dict(calls[message["full_query_id"]])
            if provider == "afrislm":
                reference = references[message["id"]]
                assert reference["original"] == message["text"]
                full["translation"] = reference["translation"]
                full["elapsed_ms"] = reference["elapsed_ms"]
            else:
                expected = letter_ranges(full["translation"])
                if expected != full["native_target_word_ranges"]:
                    boundary_differences.append({"id": message["id"], "translation": full["translation"],
                        "native": full["native_target_word_ranges"], "qa": expected})
            # This compatibility field is consumed by the shared evaluator, but
            # its values here are explicitly QA approximations, never native proof.
            full["native_target_word_ranges"] = letter_ranges(full["translation"])
            current = dict(calls)
            current[message["full_query_id"]] = full
            candidates, reasons = aligned(message, current)
            accepted, rejected = [], []
            for candidate in candidates:
                reason = protected(candidate, message)
                if reason:
                    rejected.append(dict(candidate, protection_rejection=reason))
                else:
                    accepted.append(candidate)
            count = len(message["native_source_word_ranges"])
            arms = {}
            for arm, kinds in ARMS.items():
                eligible = [c for c in accepted if set(c["arms"]) & kinds]
                projections = []
                for density in freeze["requested_depths"]:
                    budget = min(count-1, max(1, math.ceil(count*density))) if count else 0
                    spans, used, competition = select(eligible, budget)
                    changed = sum(s["changed_source_words"] for s in spans)
                    projections.append({"requested_density": density, "word_budget": budget,
                        "spans": spans, "visible": mixed(message["text"], spans),
                        "actual_depth": used/count if count else 0,
                        "changed_depth": changed/count if count else 0,
                        "changed_source_words": changed, "covered_source_words": used,
                        "competing_claims_rejected": competition})
                queries = {c["query_id"] for c in message["candidates"] if set(c["arms"]) & kinds}
                arms[arm] = {"projections": projections, "eager_distinct_chunk_queries": len(queries),
                    "eager_sum_measured_call_ms": full["elapsed_ms"] + sum(calls[q]["elapsed_ms"] for q in queries)}
            rows.append({"id": message["id"], "source": "en", "target": "sw",
                "corpus": message["corpus"], "length_bin": message["length_bin"],
                "original": message["text"], "source_words": count,
                "native_source_word_ranges": message["native_source_word_ranges"],
                "full_translation": full["translation"], "full_reference_provider": provider,
                "candidate_rejections": reasons, "protection_rejections": rejected,
                "aligned_candidates": accepted, "arms": arms})
        output = {"schema": "vipi-cached-chunk-reference-comparison-1", "production": False,
            "semantic_review": False, "freeze_sha256": sha(args.freeze), "runner_sha256": sha(__file__),
            "full_reference_provider": provider, "target_boundary_source": "QA Unicode approximation; not native",
            "old_native_boundary_differences": boundary_differences, "rows": rows}
        path = args.output_dir / (provider + "-reference-r01.json")
        assert not path.exists()
        path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
        print(provider, "boundary differences", len(boundary_differences), "rows", len(rows))


if __name__ == "__main__":
    main()
