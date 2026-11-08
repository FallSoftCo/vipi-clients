#!/usr/bin/env python3
"""Prepare source-aware, provider-masked full/reference-focus review packets.

Input selections and the independent24 subset were frozen before new output.
This file does not judge correctness or expose provider names in review rows.
"""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "review-freeze", "mlkit", "afrislm", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.source.read_text())
    freeze = json.loads(args.review_freeze.read_text())
    assert sha(args.source) == freeze["source_protocol_sha256"]
    assert len(source["cases"]) == 80
    inputs = {name: json.loads(getattr(args, name).read_text()) for name in ("mlkit", "afrislm")}
    records = {name: {row["id"]: row for row in value["rows"]} for name, value in inputs.items()}
    assert all(set(records[name]) == {row["id"] for row in source["cases"]} for name in records)
    packets, secondary_packets, keys = [], [], []
    for case in source["cases"]:
        order = ["mlkit", "afrislm"]
        if hashlib.sha256(("vipi-bst-masked-provider-order-r01:" + case["id"]).encode()).digest()[0] & 1:
            order.reverse()
        output = {"id": case["id"], "source": case["text"], "source_language": "en", "target_language": "sw",
            "sampling_length_bin": case["sampling_length_bin"],
            "review_only_preceding_context": case["review_only_preceding_context"],
            "context_note": "No preceding context was supplied to either provider. Indicate whether your meaning judgment needs it."}
        secondary = {"id": case["id"], "source": case["text"], "sampling_length_bin": case["sampling_length_bin"]}
        key = {"id": case["id"]}
        for slot, name in zip(("A", "B"), order):
            row = records[name][case["id"]]
            assert row["original"] == case["text"]
            projection = next(p for p in row["arms"]["window"]["projections"] if p["requested_density"] == 0.1)
            output[slot] = {"full_reference": row["full_translation"], "mixed_text": projection["visible"],
                "native_source_word_ranges": row["native_source_word_ranges"],
                "requested_density": 0.1, "source_word_count": row["source_words"],
                "target_boundary_caveat": inputs[name]["target_boundary_source"],
                "selected_spans": [{field: span[field] for field in (
                    "sourceStartUTF16", "sourceEndUTF16", "targetStartUTF16", "targetEndUTF16",
                    "original", "translated", "source_words", "changed_source_words", "isolated_translation")}
                    for span in projection["spans"]]}
            secondary[slot] = {"full_reference": row["full_translation"], "projections": [
                {"requested_density": p["requested_density"], "mixed_text": p["visible"],
                 "selected_spans": [{field: span[field] for field in (
                     "sourceStartUTF16", "sourceEndUTF16", "targetStartUTF16", "targetEndUTF16",
                     "original", "translated", "source_words", "changed_source_words", "isolated_translation")}
                     for span in p["spans"]]}
                for p in row["arms"]["window"]["projections"] if p["requested_density"] in (0.25, 0.5)]}
            key[slot] = name
        packets.append(output)
        secondary_packets.append(secondary)
        keys.append(key)
    header = {"schema": "vipi-conversational-masked-review-1", "production": False,
        "source_protocol_sha256": sha(args.source), "review_freeze_sha256": sha(args.review_freeze),
        "runner_sha256": sha(Path(__file__)),
        "instructions": "Judge both full references and each selected10%-window focus separately; use correct/material/wrong_scope/minor/uncertain for spans. Record unchanged/no-useful-span, numbers/names, literal sense errors and context requirements explicitly. Do not infer correctness from substring agreement or fluency. Freeze labels before viewing the separate provider key."}
    args.output_dir.mkdir(exist_ok=True)
    chosen = set(freeze["independent_subset_ids"])
    subset = [row for row in packets if row["id"] in chosen]
    assert len(subset) == len(chosen) == 24
    values = {
        "all-80-masked.json": dict(header, rows=packets),
        "independent-24-masked.json": dict(header, rows=subset),
        "secondary-80-masked.json": dict(header,
            instructions="Review secondary25/50% window projections after freezing primary10% labels. Keep provider key hidden; source context is in the corresponding primary packet.",
            rows=secondary_packets),
        "provider-key.json": {"rows": keys, "input_bindings": {name: sha(getattr(args, name)) for name in records}}
    }
    for name, value in values.items():
        path = args.output_dir / name
        assert not path.exists(), "Preserve frozen review packets"
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        print(name, sha(path))


if __name__ == "__main__":
    main()
