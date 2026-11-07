#!/usr/bin/env python3
"""Project captured normalized-input spans onto unchanged original messages.

An alias expansion is indivisible: a target for only "way" in "btw"→"by the
way" cannot claim the original abbreviation. This measures a QA arm only.
"""
import argparse
import copy
import json
from pathlib import Path
import statistics

from compare import depth, digest, mixed


def original_range(start, end, segments):
    if not segments or not (0 <= start < end <= segments[-1]["normalized_range"][1]):
        return None
    output = []
    for segment in segments:
        a, b = segment["normalized_range"]
        x, y = segment["original_range"]
        left, right = max(a, start), min(b, end)
        if left >= right:
            continue
        if segment["kind"] != "unchanged":
            if left != a or right != b:
                return None
            output.append((x, y))
        else:
            output.append((x + left - a, x + right - a))
    if not output or any(a[1] != b[0] for a, b in zip(output, output[1:])):
        return None
    return output[0][0], output[-1][1]


def project(original, spans, segments):
    raw = original.encode("utf-16-le")
    accepted, rejected = [], []
    for span in spans:
        bounds = original_range(span["sourceStartUTF16"], span["sourceEndUTF16"], segments)
        if bounds is None:
            rejected.append({"span": span, "reason": "partial_or_discontinuous_normalization_edit"})
            continue
        start, end = bounds
        try:
            source = raw[start*2:end*2].decode("utf-16-le")
        except UnicodeError:
            rejected.append({"span": span, "reason": "nonunicode_original_boundary"})
            continue
        accepted.append({**span, "sourceStartUTF16": start, "sourceEndUTF16": end, "original": source,
                         "normalized_source": span["original"],
                         "normalized_source_range": [span["sourceStartUTF16"], span["sourceEndUTF16"]]})
    return accepted, rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-comparison", type=Path, required=True)
    parser.add_argument("--normalized-comparison", type=Path, required=True)
    parser.add_argument("--normalized-protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite retained result")
    base = json.loads(args.base_comparison.read_text())
    alternate = json.loads(args.normalized_comparison.read_text())
    protocol = json.loads(args.normalized_protocol.read_text())
    assert alternate["input_sha256"] == digest(args.normalized_protocol)
    assert base["input_sha256"] == protocol["source_protocol_sha256"]
    key = lambda row: (row["id"], row["source"], row["target"])
    inputs = {key(row): row for row in protocol["cases"]}
    captures = {key(row): row for row in alternate["results"]}
    assert set(inputs) == set(captures)
    results = []
    for previous in base["results"]:
        index = key(previous)
        if index not in inputs:
            results.append({**previous, "normalization_changed": False})
            continue
        source, capture = inputs[index], captures[index]
        assert source["original_text"] == previous["original"]
        assert source["text"] == capture["original"]
        row = copy.deepcopy(capture)
        row.update(original=previous["original"], text=previous["original"], normalized_input=source["text"],
                   normalization_changed=True, native_word_ranges=previous["native_word_ranges"],
                   semantic_assessment="pending_normalized_author_review")
        for arm in ("A", "B"):
            spans, rejected = project(previous["original"], capture[arm]["spans"], source["normalization_segments"])
            row[arm].update(spans=spans, visible=mixed(previous["original"], spans),
                            depth=depth(spans, previous["native_word_ranges"]), projection_rejections=rejected)
        results.append(row)
    summary = {}
    for target in ("es", "sw"):
        rows = [row for row in results if row["target"] == target]
        summary["en-" + target] = {"messages": len(rows), "normalized_messages": sum(row["normalization_changed"] for row in rows),
            **{arm: {"messages_with_span": sum(bool(row[arm]["spans"]) for row in rows),
                     "spans": sum(len(row[arm]["spans"]) for row in rows),
                     "mean_original_native_word_depth": statistics.mean(row[arm]["depth"] for row in rows)} for arm in ("A", "B")}}
    report = {"schema": "vipi-normalized-original-projection-1", "production": False,
              "base_comparison_sha256": digest(args.base_comparison), "normalized_comparison_sha256": digest(args.normalized_comparison),
              "protocol_sha256": digest(args.normalized_protocol), "runner_sha256": digest(__file__),
              "semantic_review": "Pending; unchanged rows reuse prior evidence, edited rows require paired review",
              "summary": summary, "results": results}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
