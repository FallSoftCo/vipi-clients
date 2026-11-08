#!/usr/bin/env python3
"""Recompute direct-extension summary from explicit author labels, not MT agreement."""
import argparse
import collections
import hashlib
import json
import statistics
from pathlib import Path


def scope(span):
    return tuple(span[k] for k in ("sourceStartUTF16", "sourceEndUTF16", "targetStartUTF16", "targetEndUTF16"))


def summaries(comparison, review):
    labels = {(r["id"], r["target"], scope(s)): s["label"] for r in review["rows"] for s in r["spans"]}
    result = []
    for target in sorted({r["target"] for r in comparison["rows"]}):
        for corpus in ["all", *sorted({r["corpus"] for r in comparison["rows"]})]:
            for length in ("all", "1-5", "6-15", "16-30", "31+"):
                rows = [r for r in comparison["rows"] if r["target"] == target
                        and (corpus == "all" or r["corpus"] == corpus)
                        and (length == "all" or r["length_bin"] == length)]
                if not rows:
                    continue
                for arm in ("word", "window", "split", "union"):
                    for density in (.1, .25, .5):
                        counts = collections.Counter()
                        clean = useful = material = uncertain = 0
                        depth, minor_depth, changed = [], [], []
                        for row in rows:
                            p = next(p for p in row["arms"][arm]["projections"] if p["requested_density"] == density)
                            values = [labels[row["id"], target, scope(s)] for s in p["spans"]]
                            counts.update(values)
                            correct = sum(s["changed_source_words"] for s, label in zip(p["spans"], values) if label == "correct")
                            acceptable = sum(s["changed_source_words"] for s, label in zip(p["spans"], values) if label in ("correct", "minor"))
                            depth.append(correct/row["source_words"])
                            minor_depth.append(acceptable/row["source_words"])
                            changed.append(p["changed_depth"])
                            useful += correct > 0
                            clean += correct > 0 and all(label in ("correct", "proper_name") for label in values)
                            material += any(label in ("material", "wrong_scope") for label in values)
                            uncertain += "uncertain" in values
                        result.append({"target": target, "corpus": corpus, "length_bin": length, "arm": arm,
                                       "density": density, "messages": len(rows), "messages_with_correct_changed_word": useful,
                                       "strict_clean_useful_messages": clean, "messages_with_material_or_scope_error": material,
                                       "messages_with_uncertain_span": uncertain, "span_labels": dict(counts),
                                       "mean_changed_depth": statistics.mean(changed),
                                       "mean_correct_changed_depth": statistics.mean(depth),
                                       "mean_correct_or_minor_changed_depth": statistics.mean(minor_depth)})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    review = json.loads(args.review.read_text())
    assert review["comparison_sha256"] == hashlib.sha256(args.comparison.read_bytes()).hexdigest()
    review["summary"] = summaries(json.loads(args.comparison.read_text()), review)
    review["scorer_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.write_text(json.dumps(review, ensure_ascii=False, indent=2)+"\n")


if __name__ == "__main__":
    main()
