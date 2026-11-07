#!/usr/bin/env python3
"""Stratify inspected immersion by message length, without changing the sample."""
import argparse
import collections
import json
from pathlib import Path
import statistics

from compare import depth, digest


def bucket(count):
    return "1-5" if count <= 5 else "6-15" if count <= 15 else "16-30" if count <= 30 else "31+"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite retained result")
    data = json.loads(args.comparison.read_text())
    report, errors = {}, []
    for lang, name in [("es", "spanish"), ("sw", "swahili")]:
        review = json.loads((Path(__file__).parent / (name + "-200-author-review.json")).read_text())
        assert review["comparison_sha256"] == digest(args.comparison)
        reviews = {row["id"]: row for row in review["rows"]}
        groups = collections.defaultdict(list)
        for row in data["results"]:
            if row["target"] != lang:
                continue
            review_row = reviews[row["id"]]
            value = {"id": row["id"], "word_count": len(row["native_word_ranges"]), "C_full": review_row["C_full"]["label"]}
            for arm in ["A", "B"]:
                labels = review_row["A_spans"] + (review_row["B_added_spans"] if arm == "B" else [])
                by_range = {tuple(label["source_range"]): label for label in labels}
                accepted = [span for span in row[arm]["spans"] if by_range[(span["sourceStartUTF16"], span["sourceEndUTF16"])]["label"] == "meaning_appears_correct"]
                bad = sum(label["label"] in {"material_error", "lexical_category_error"} for label in labels)
                value[arm] = {"mixed_depth_all_spans": depth(row[arm]["spans"], row["native_word_ranges"]),
                              "accepted_depth": depth(accepted, row["native_word_ranges"]),
                              "clean_useful": bool(accepted) and bad == 0, "bad_spans": bad,
                              "accepted_spans": len(accepted)}
            for arm, labels in [("A", review_row["A_spans"]), ("B_added", review_row["B_added_spans"])]:
                for label in labels:
                    if label["label"] not in {"material_error", "lexical_category_error"}:
                        continue
                    alignment_only = lang == "es" and row["id"] == "uci-sms-line-1432" and label["source"] == "hurry"
                    errors.append({"id": row["id"], "pair": "en-" + lang, "arm": arm, "original": row["original"],
                                   "full_translation": row["translation"], "span": label,
                                   "observed_cause": "alignment_drops_valid_multiword_verb_scope" if alignment_only else "same_wrong_sense_or_role_present_in_full_provider_output",
                                   "basis": "Author compared full source and actual full provider output with selected span; no independent bilingual acceptance."})
            groups[bucket(value["word_count"])].append(value)
        pair = {}
        for key in ("1-5", "6-15", "16-30", "31+"):
            rows = groups[key]
            if not rows:
                continue
            pair[key] = {"messages": len(rows), "native_word_count_total": sum(row["word_count"] for row in rows),
                         "C_full_labels": dict(collections.Counter(row["C_full"] for row in rows))}
            for arm in ["A", "B"]:
                pair[key][arm] = {
                    "clean_useful_messages": sum(row[arm]["clean_useful"] for row in rows),
                    "messages_with_accepted_span": sum(row[arm]["accepted_spans"] > 0 for row in rows),
                    "accepted_spans": sum(row[arm]["accepted_spans"] for row in rows),
                    "clear_bad_spans": sum(row[arm]["bad_spans"] for row in rows),
                    "macro_mean_mixed_word_depth": statistics.mean(row[arm]["mixed_depth_all_spans"] for row in rows),
                    "macro_mean_accepted_word_depth": statistics.mean(row[arm]["accepted_depth"] for row in rows),
                    "median_accepted_word_depth": statistics.median(row[arm]["accepted_depth"] for row in rows),
                    "word_weighted_accepted_depth": sum(row[arm]["accepted_depth"] * row["word_count"] for row in rows) / max(1, sum(row["word_count"] for row in rows)),
                }
        report["en-" + lang] = pair
    value = {"schema": "vipi-length-stratified-author-evaluation-1", "comparison_sha256": digest(args.comparison),
             "runner_sha256": digest(__file__), "unit": "Message (may contain multiple sentences); native Android source word count",
             "assessment": "Author labels, not independent bilingual acceptance; old SMS is diagnostic only",
             "summary": report, "clear_error_cause_counts": dict(collections.Counter(row["observed_cause"] for row in errors)), "errors": errors}
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"summary": report, "causes": value["clear_error_cause_counts"]}, indent=2))


if __name__ == "__main__":
    main()
