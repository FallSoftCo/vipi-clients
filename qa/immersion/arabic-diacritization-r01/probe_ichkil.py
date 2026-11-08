"""Same frozen diagnostic, original pinned pipeline; direct local ONNX only."""
import hashlib
import importlib.util
import json
import os
import platform
import resource
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
import numpy as np
import onnxruntime as ort

output = ROOT / "capture-ichkil-r01.json"
assert not output.exists()
plan = json.loads((ROOT / "plan-r01.json").read_text())
for entry in json.loads((ROOT / "retrieval.json").read_text()):
    assert hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest() == entry["sha256"]
pipeline = ROOT / "ichkil-python/src/ichkil/pipeline.py"
spec = importlib.util.spec_from_file_location("ichkil_pinned_pipeline", pipeline)
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
config = json.loads((ROOT / "ichkil-model/config.json").read_text())
opts = ort.SessionOptions()
opts.intra_op_num_threads = 1
opts.inter_op_num_threads = 1
opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
result = {
    "schema": "vipi-private-arabic-diacritizer-capture-1",
    "model": "ichkil0.3.0",
    "runtime": ort.__version__,
    "numpy": np.__version__,
    "host": platform.platform(),
    "threads": 1,
    "plan_sha256": hashlib.sha256((ROOT / "plan-r01.json").read_bytes()).hexdigest(),
    "extension_sha256": hashlib.sha256((ROOT / "extension-ichkil-r01.json").read_bytes()).hexdigest(),
    "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "scope": "Exact upstream normalization/labels via direct local ONNX; no HF auto-download/import. Raw output only, not native integration or approved reading.",
    "cases": [],
}
start = time.perf_counter()
try:
    session = ort.InferenceSession(str(ROOT / "ichkil-model/model.onnx"), sess_options=opts, providers=["CPUExecutionProvider"])
except Exception as exc:
    result.update(completed=False, load_error=str(exc), load_error_type=type(exc).__name__)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"path": str(output), "load_error": str(exc)}))
    sys.exit(1)
result["load_ms"] = (time.perf_counter() - start) * 1000
result["providers"] = session.get_providers()
vowels = {chr(c) for c in range(0x064B, 0x0653)} | {"ٰ"}


def skeleton(text):
    return "".join(c for c in unicodedata.normalize("NFC", text) if c not in vowels)


def predict(text):
    base = P.strip_diacritics(text.strip())
    ids = P.encode(base, config["sym2id"], config["sym2id"].get("<unk>", 1))
    (logits,) = session.run(["logits"], {"input_ids": np.asarray([ids], dtype=np.int64)})
    flat = logits[0].reshape(-1).tolist()
    n = int(config["num_tags"])
    labels = [P.argmax(flat[i * n:(i + 1) * n]) for i in range(len(base))]
    return P.attach(base, labels)


for case in plan["cases"]:
    start = time.perf_counter()
    first = predict(case["source"])
    first_ms = (time.perf_counter() - start) * 1000
    start = time.perf_counter()
    warm = predict(case["source"])
    warm_ms = (time.perf_counter() - start) * 1000
    result["cases"].append({**case, "output": first, "warm_identical": first == warm, "first_ms": first_ms, "warm_ms": warm_ms, "nfc_source_skeleton_preserved": skeleton(first) == skeleton(case["source"])})
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
result.update(completed=True, peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"path": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "cases": len(result["cases"]), "load_ms": result["load_ms"], "max_first_ms": max(c["first_ms"] for c in result["cases"]), "max_warm_ms": max(c["warm_ms"] for c in result["cases"]), "peak_rss_kib": result["peak_rss_kib"]}))
