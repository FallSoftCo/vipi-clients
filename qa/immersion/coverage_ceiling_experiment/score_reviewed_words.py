#!/usr/bin/env python3
"""Exact scope-label join for source-only word research; no semantic inference."""
import argparse
import hashlib
import json
from pathlib import Path


def scope(span):
    return span["sourceStartUTF16"], span["sourceEndUTF16"], span["original"], span["translated"]


def main():
    parser = argparse.ArgumentParser()
    for key in ("capture", "review", "freeze", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    capture, review, freeze = (json.loads(p.read_text()) for p in (args.capture, args.review, args.freeze))
    labels = {(r["id"], scope(s)): s["semantic_label"] for r in review["rows"] for s in r["scopes"]}
    rows = []
    for row in capture["rows"]:
        for arm, projection in row["arms"].items():
            spans = [dict(s, semantic_label=labels[row["id"], scope(s)]) for s in projection["spans"]]
            correct = sum(s["semantic_label"] == "correct" for s in spans)
            bad = any(s["semantic_label"] in ("material", "wrong_scope") for s in spans)
            uncertain = any(s["semantic_label"] == "uncertain" for s in spans)
            rows.append(dict(id=row["id"], source=row["text"], arm=arm, length_bin=row["sampling_length_bin"],
                source_words=row["source_words"], mixed_text=projection["mixed_text"], spans=spans,
                correct_depth=correct/row["source_words"] if row["source_words"] else 0,
                clean_useful=bool(correct) and not bad and not uncertain, material_error=bad, uncertain=uncertain))
    summaries = []
    for arm in capture["summaries"]:
        for length in ("all", "1-5", "6-15", "16-30"):
            group = [r for r in rows if r["arm"] == arm and (length == "all" or r["length_bin"] == length)]
            summaries.append(dict(arm=arm, length_bin=length, messages=len(group),
                clean_useful_messages=sum(r["clean_useful"] for r in group),
                material_error_messages=sum(r["material_error"] for r in group),
                uncertain_messages=sum(r["uncertain"] for r in group),
                mean_correct_changed_depth=sum(r["correct_depth"] for r in group)/len(group),
                content_spans=sum(s["category"] == "content" for r in group for s in r["spans"]),
                function_spans=sum(s["category"] == "function" for r in group for s in r["spans"])))
    primary = next(r for r in summaries if r["arm"] == "one_prefer_content" and r["length_bin"] == "all")
    content = next(r for r in summaries if r["arm"] == "one_content" and r["length_bin"] == "all")
    limits = freeze["research_advance_only"]
    passed = (primary["clean_useful_messages"] >= limits["primary_clean_useful_at_least"]
              and primary["material_error_messages"] <= limits["primary_material_or_scope_errors_at_most"]
              and content["clean_useful_messages"] >= limits["one_content_clean_useful_at_least"])
    output = dict(schema="vipi-source-only-word-decision-1", production=False, provider_calls=0,
        research_threshold_passed=passed,
        decision="Sparse100-entry research seed; not an estimate of the maximum dictionary approach. No production promotion from this sample.",
        input_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.capture, args.review, args.freeze)},
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), summaries=summaries,
        timing=capture["timing"], rows=rows)
    assert not args.output.exists()
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps([s for s in summaries if s["length_bin"] == "all"], indent=2))


if __name__ == "__main__":
    main()
