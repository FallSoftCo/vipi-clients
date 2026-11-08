#!/usr/bin/env python3
"""Pinned native Bergamot CPU provider experiment, not a mobile integration."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import time
from pathlib import Path

import yaml
from bergamot import Service, ServiceConfig, ResponseOptions, VectorString


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def memory():
    return {line.split(":", 1)[0]: line.split(":", 1)[1].strip()
            for line in Path("/proc/self/status").read_text().splitlines()
            if line.startswith(("VmRSS:", "VmHWM:", "VmSize:", "Threads:"))}


def main():
    p = argparse.ArgumentParser()
    for name in ("protocol", "config", "model-receipt", "output"):
        p.add_argument("--"+name, type=Path, required=True)
    p.add_argument("--target", choices=["sw", "es"], required=True)
    p.add_argument("--beam", type=int, choices=[1, 12], default=12)
    args = p.parse_args()
    assert not args.output.exists(), "Preserve prior capture"
    protocol = json.loads(args.protocol.read_text())
    rows = [r for r in protocol["messages"] if r["source"] == "en" and r["target"] == args.target]
    assert len(rows) == 80 and len({r["id"] for r in rows}) == 80
    assert all("\n" not in r["text"] and "\r" not in r["text"] for r in rows), "Language tag must qualify every paragraph"
    receipt = json.loads(args.model_receipt.read_text())
    for file in receipt["files"]:
        path = Path(file["path"])
        assert path.stat().st_size == file["bytes"] and sha(path) == file["sha256"]
    config = yaml.safe_load(args.config.read_text())
    config.pop("shortlist", None)
    config.update({"beam-size": args.beam, "cpu-threads": 2, "mini-batch-words": 1536,
                   "max-length-break": 512, "workspace": 128})
    result = {"schema": "vipi-qvac-nano-native-provider-1", "production": False,
              "mobile_runtime_qualified": False, "semantic_acceptance": False,
              "input_sha256": sha(args.protocol), "model_receipt_sha256": sha(args.model_receipt),
              "model": receipt, "config": config, "runner_sha256": sha(__file__),
              "provider": "Native Bergamot0.4.5 CPU, no shortlist,2threads,1worker",
              "python": os.sys.version, "runtime": {p: importlib.metadata.version(p) for p in ("bergamot", "PyYAML", "requests")},
              "source_preprocessing": "Exact original text with one model-required ##SW or ##ES prefix; paragraph splitting only; no slang normalization.",
              "memory_before_load": memory(), "complete": False, "cases": [], "started_unix": time.time()}
    def save():
        temporary = args.output.with_suffix(".partial")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
        temporary.replace(args.output)
    save()
    start = time.perf_counter()
    service = Service(ServiceConfig(numWorkers=1, cacheSize=0, logLevel="err"))
    model = service.modelFromConfig(yaml.safe_dump(config))
    result["model_load_ms"] = (time.perf_counter()-start)*1000
    result["memory_after_load"] = memory()
    options = ResponseOptions(alignment=False, qualityScores=False)
    for index, row in enumerate(rows):
        start = time.perf_counter()
        response = service.translate(model, VectorString(["##"+args.target.upper()+" "+row["text"]]), options)[0]
        elapsed = (time.perf_counter()-start)*1000
        result["cases"].append({"id": row["id"], "source": "en", "target": args.target,
                                "corpus": row["corpus"], "length_bin": row["length_bin"],
                                "original": row["text"], "translation": response.target.text,
                                "provider_source": response.source.text, "elapsed_ms": elapsed,
                                "native_source_word_ranges": row["native_source_word_ranges"]})
        result["memory_latest"] = memory()
        save()
        print(f"{index+1}/80", flush=True)
    result["complete"] = True
    result["finished_unix"] = time.time()
    save()


if __name__ == "__main__":
    main()
