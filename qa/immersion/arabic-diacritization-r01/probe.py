"""Bounded, private CPU feasibility capture; never mutates app/source text."""
import argparse
import hashlib
import json
import os
import platform
import resource
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "text2tashkeel"))
os.environ["TT_ORT_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

parser = argparse.ArgumentParser()
parser.add_argument("model", choices=["rawi-v2-int8", "libtashkeel"])
args = parser.parse_args()
destination = ROOT / f"capture-{args.model}-r01.json"
assert not destination.exists(), "Retain prior output; do not overwrite a capture."
plan_path = ROOT / "plan-r01.json"
plan_sha = hashlib.sha256(plan_path.read_bytes()).hexdigest()
assert plan_sha == "be5104c2183b4a52b18b61b79e51b290926bf852b6b34a7f1cc895d9e2b7ecd3"
plan = json.loads(plan_path.read_text())
for entry in json.loads((ROOT / "retrieval.json").read_text()):
    path = Path(entry["path"])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], path

import numpy
import onnxruntime
from text2tashkeel import Diacritizer

start = time.perf_counter()
reader = Diacritizer(
    args.model,
    providers=["CPUExecutionProvider"],
    preserve_orthography=True,
    respect_existing=True,
    allow_restoration=False,
    waqf=False,
)
backend = reader.backend
load_ms = (time.perf_counter() - start) * 1000
marks = {chr(c) for c in range(0x064B, 0x0653)} | {"ٰ"}


def skeleton(text):
    return "".join(c for c in unicodedata.normalize("NFC", text) if c not in marks)


result = {
    "schema": "vipi-private-arabic-diacritizer-capture-1",
    "model": args.model,
    "plan_sha256": plan_sha,
    "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "runtime": onnxruntime.__version__,
    "numpy": numpy.__version__,
    "python": sys.version,
    "host": platform.platform(),
    "threads": 1,
    "providers": backend.sess.get_providers(),
    "load_ms": load_ms,
    "options": {
        "preserve_orthography": True,
        "respect_existing": True,
        "allow_restoration": False,
        "waqf": False,
    },
    "limits": [
        "Raw upstream outputs, not approved native full readings.",
        "Libtashkeel wrapper ignores the three rawi-specific decoding options.",
        "Small authored/reused diagnostic, not corpus accuracy or bilingual gold.",
        "Whole-process Linux CPU peak includes imports/model; not mobile memory.",
    ],
    "cases": [],
}
for case in plan["cases"]:
    begin = time.perf_counter()
    first = reader.diacritize(case["source"])
    first_ms = (time.perf_counter() - begin) * 1000
    begin = time.perf_counter()
    warm = reader.diacritize(case["source"])
    warm_ms = (time.perf_counter() - begin) * 1000
    result["cases"].append({
        **case,
        "output": first,
        "warm_identical": first == warm,
        "first_ms": first_ms,
        "warm_ms": warm_ms,
        "nfc_source_skeleton_preserved": skeleton(first) == skeleton(case["source"]),
    })
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
result["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
result["completed"] = True
destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({
    "path": str(destination),
    "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
    "model": args.model,
    "cases": len(result["cases"]),
    "warm_identical": sum(c["warm_identical"] for c in result["cases"]),
    "skeleton_preserved": sum(c["nfc_source_skeleton_preserved"] for c in result["cases"]),
    "load_ms": load_ms,
    "max_first_ms": max(c["first_ms"] for c in result["cases"]),
    "max_warm_ms": max(c["warm_ms"] for c in result["cases"]),
    "peak_rss_kib": result["peak_rss_kib"],
}))
