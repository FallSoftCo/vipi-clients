#!/usr/bin/env python3
"""Validate a complete physical Apple capture for native alignment replay.

Preserves the raw report separately and binds every row to the authored corpus.
Conversion adds schema fields only; it never edits a translation.
"""
import argparse
import hashlib
import json
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--capture", type=Path, required=True)
p.add_argument("--corpus", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--require-offline", action="store_true")
a = p.parse_args()
raw = a.capture.read_bytes(); r = json.loads(raw); corpus = json.loads(a.corpus.read_bytes())
assert r["finished"] is True and r["preparation"] is False
assert r["status"] == "Finished 90 directions. 0 failed."
languages = corpus["languages"]
expected = {(s, t) for s in languages for t in languages if s != t}
assert len(r["results"]) == len(expected) == 90
assert {(p["source"], p["target"]) for p in r["results"]} == expected
cases = {s["id"]: s["text"] for s in corpus["cases"]}
offline = r["offline_required"] is True
if a.require_offline:
    assert offline
for pair in r["results"]:
    source, target = pair["source"], pair["target"]
    assert pair["status"] == "executed"
    assert (pair["sessionSource"], pair["sessionTarget"]) == (source, target)
    assert len(pair["samples"]) == len(cases)
    assert {s["id"] for s in pair["samples"]} == set(cases)
    if offline:
        assert pair["networkAvailable"] is False
    for sample in pair["samples"]:
        assert sample["original"] == cases[sample["id"]][source]
        assert sample["translation"].strip()
        assert sample["latency_ms"] > 0
        if offline:
            assert sample["networkBefore"] is False and sample["networkAfter"] is False
        sample["status"] = "executed"
        sample["reference"] = cases[sample["id"]][target]
r.update(provider="Apple Translation", platform="Physical iPad / iPadOS " + r["systemVersion"],
         raw_capture_sha256=hashlib.sha256(raw).hexdigest(), network_absence_verified=offline,
         capture_conversion="Schema normalization only; all actual translation text preserved",
         linguistic_acceptance=False)
with a.output.open("x") as output:
    json.dump(r, output, ensure_ascii=False, indent=2); output.write("\n")
print(json.dumps({"pairs": len(expected), "samples": len(expected) * len(cases),
                  "network_absence_verified": offline, "run_id": r["run_id"],
                  "raw_capture_sha256": r["raw_capture_sha256"]}))
