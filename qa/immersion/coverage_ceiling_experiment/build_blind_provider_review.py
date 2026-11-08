#!/usr/bin/env python3
"""Mask provider identity in a preselected local-translation comparison.

This does not make previously inspected source/reference rows an unseen test.
Keep the provider key separate until labels are recorded.
"""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    assert not path.exists(), f"Preserve prior artifact: {path}"
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    for name in ("capture", "baseline", "freeze", "output-dir"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    capture = json.loads(args.capture.read_text())
    baseline = json.loads(args.baseline.read_text())
    freeze = json.loads(args.freeze.read_text())
    assert capture["complete"] and len(capture["cases"]) == 80
    assert capture["input_sha256"] == freeze["source_protocol_sha256"]
    refs = {r["id"]: r for r in baseline["rows"] if r["target"] == "sw"}
    rows, key = [], []
    for new in capture["cases"]:
        old = refs[new["id"]]
        assert old["original"] == new["original"]
        flipped = hashlib.sha256(("vipi-slm-provider-order-r01:" + new["id"]).encode()).digest()[0] & 1
        providers = ["afrislm", "mlkit"] if flipped else ["mlkit", "afrislm"]
        values = {"afrislm": new["translation"], "mlkit": old["full_translation"]}
        rows.append({"id": new["id"], "corpus": new["corpus"], "source": new["original"],
                     "A": values[providers[0]], "B": values[providers[1]]})
        key.append({"id": new["id"], "A": providers[0], "B": providers[1],
                    "afrislm_status": new["status"]})
    header = {"schema": "vipi-masked-provider-review-input-1", "production": False,
              "capture_sha256": sha(args.capture), "baseline_sha256": sha(args.baseline),
              "freeze_sha256": sha(args.freeze), "runner_sha256": sha(__file__),
              "status": "Inspected development sources, provider identity masked; previously seen baseline outputs may be recognized.",
              "instructions": "Judge A and B separately for broad meaning preservation, material error, uncertainty or unchanged text. Preserve actual numbers, names and conversational sense. Record labels before opening provider-key.json. Do not treat fluency alone as correctness."}
    args.output_dir.mkdir(exist_ok=True)
    write(args.output_dir / "all-80-masked.json", dict(header, rows=rows))
    chosen = set(freeze["independent_subset_ids"])
    subset = [r for r in rows if r["id"] in chosen]
    assert len(subset) == 24
    write(args.output_dir / "independent-24-masked.json", dict(header, rows=subset))
    write(args.output_dir / "provider-key.json", {"rows": key})


if __name__ == "__main__":
    main()
