#!/usr/bin/env python3
"""Score exact frozen labels for development shortening; never infer correctness."""
import argparse
import hashlib
import json
from pathlib import Path

from compare_constituent_conservation import scope


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bindings = {}

    def read(name):
        path = args.evidence / name
        bindings[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return json.loads(path.read_text())

    labels = {}
    for row in read("primary-decision-r01.json")["rows"] + read("secondary-decision-r01.json")["rows"]:
        for span in row["spans"]:
            k = row["provider"], row["id"], scope(span)
            value = span.get("label", span.get("semantic_label"))
            assert k not in labels or labels[k] == value
            labels[k] = value
    for row in read("constituent-shortening-new-scope-review-r01.json")["rows"]:
        k = row["provider"], row["id"], scope(row["after"])
        assert k not in labels
        labels[k] = row["label"]
    rows = read("constituent-shortening-r01.json")["rows"]
    for row in rows:
        for phase in ("before", "after"):
            selected = []
            for trace in row["traces"]:
                span = trace[phase]
                if span is not None:
                    label = labels[row["provider"], row["id"], scope(span)]
                    selected.append(dict(span, semantic_label=label))
            correct = sum(s["changed_source_words"] for s in selected if s["semantic_label"] == "correct")
            bad = any(s["semantic_label"] in ("material", "wrong_scope") for s in selected)
            uncertain = any(s["semantic_label"] == "uncertain" for s in selected)
            row[phase + "_review"] = dict(spans=selected, correct_depth=correct/row["source_words"] if row["source_words"] else 0,
                clean_useful=bool(correct) and not bad and not uncertain, material_or_scope_error=bad, uncertain=uncertain)
    summaries = []
    for provider in ("mlkit", "afrislm"):
        for density in (0.1, 0.25, 0.5):
            group = [r for r in rows if r["provider"] == provider and r["density"] == density]
            entry = dict(provider=provider, density=density, messages=len(group))
            for phase in ("before", "after"):
                selected = [r[phase + "_review"] for r in group]
                entry[phase] = dict(mean_correct_changed_depth=sum(r["correct_depth"] for r in selected)/len(selected),
                    clean_useful_messages=sum(r["clean_useful"] for r in selected),
                    material_or_scope_error_messages=sum(r["material_or_scope_error"] for r in selected),
                    uncertain_messages=sum(r["uncertain"] for r in selected))
            entry["bad_messages_removed"] = sum(r["before_review"]["material_or_scope_error"] and not r["after_review"]["material_or_scope_error"] for r in group)
            entry["bad_messages_introduced"] = sum(not r["before_review"]["material_or_scope_error"] and r["after_review"]["material_or_scope_error"] for r in group)
            entry["correct_depth_retained_fraction"] = entry["after"]["mean_correct_changed_depth"] / entry["before"]["mean_correct_changed_depth"]
            summaries.append(entry)
    primary = next(s for s in summaries if s["provider"] == "afrislm" and s["density"] == 0.1)
    gate = (primary["bad_messages_removed"] >= 2 and primary["bad_messages_introduced"] == 0
            and primary["correct_depth_retained_fraction"] >= 0.8)
    output = dict(schema="vipi-constituent-shortening-development-decision-1", production=False,
        primary_release_gate="Original fresh primary remains FAILED; this is post-review development diagnosis.",
        research_continuation_threshold_passed=gate, input_hashes=bindings,
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), summaries=summaries, rows=rows)
    assert not args.output.exists()
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
