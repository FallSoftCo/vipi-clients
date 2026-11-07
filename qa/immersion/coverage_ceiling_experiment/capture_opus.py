#!/usr/bin/env python3
"""Bounded CPU-only OPUS-Marian comparison on existing frozen English inputs.

No app runtime change. Retains original model/preprocessing provenance and all
provider strings independently of the production identifier/matcher gates.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import time

import ctranslate2
import sentencepiece


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalize(text, root):
    raw = text.encode()
    for name, flags in [("replace-unicode-punctuation.perl", []),
                        ("remove-non-printing-char.perl", []),
                        ("normalize-punctuation.perl", ["-l", "en"])]:
        raw = subprocess.run(["perl", str(root / "preprocessing" / name), *flags],
                             input=raw, capture_output=True, check=True, timeout=10).stdout
    return " ".join(raw.decode().split())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--protocol", type=Path, action="append", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        p.error("refusing to repeat/overwrite retained capture")
    protocols = [json.loads(path.read_text()) for path in args.protocol]
    cases = [{**r, "protocol_sha256": sha(path)} for path, protocol in zip(args.protocol, protocols)
             for r in protocol["cases"] if r["source"] == "en" and r["target"] == "sw"]
    assert len(cases) == 400 and len({r["id"] for r in cases}) == 400
    start = time.perf_counter()
    model = args.root / "converted-int8"
    source = sentencepiece.SentencePieceProcessor(model_file=str(args.root / "original/source.spm"))
    target = sentencepiece.SentencePieceProcessor(model_file=str(args.root / "original/target.spm"))
    translator = ctranslate2.Translator(str(model), device="cpu", compute_type="int8",
                                       inter_threads=1, intra_threads=2)
    load_ms = (time.perf_counter() - start) * 1000
    result = {"schema": "vipi-opus-local-provider-evaluation-1", "production": False,
              "complete": False, "model": "OPUS-MT en-sw opus-2020-01-08",
              "model_download": json.loads((args.root / "download-receipt.json").read_text()),
              "preprocessing": json.loads((args.root / "preprocessing-receipt.json").read_text()),
              "model_files": [{"name": f.name, "bytes": f.stat().st_size, "sha256": sha(f)}
                              for f in sorted(model.iterdir()) if f.is_file()],
              "sentencepiece_files": {name: sha(args.root / "original" / name)
                                      for name in ("source.spm", "target.spm")},
              "runner_sha256": sha(__file__), "load_ms": load_ms,
              "packages": {name: importlib.metadata.version(name) for name in
                           ("ctranslate2", "sentencepiece", "numpy", "PyYAML")},
              "decode": {"device": "cpu", "compute_type": "int8", "inter_threads": 1,
                         "intra_threads": 2, "beam_size": 6, "length_penalty": 1,
                         "max_decoding_length": 256, "batch_size": 1,
                         "eos": "CTranslate2 converted config add_source_eos=true; caller does not append"},
              "capacity": json.loads((args.root / "capacity.json").read_text()),
              "cases": []}
    def save():
        result["elapsed_seconds"] = time.perf_counter() - start
        result["peak_process_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        tmp = args.output.with_suffix(".partial")
        tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        tmp.replace(args.output)
    save()
    for index, case in enumerate(cases):
        began = time.perf_counter()
        normalized = normalize(case["text"], args.root)
        encoded = source.encode(normalized, out_type=str)
        before_decode = time.perf_counter()
        decoded = translator.translate_batch([encoded], beam_size=6, length_penalty=1,
                                             max_decoding_length=256, return_scores=True)[0]
        hypothesis = decoded.hypotheses[0]
        output = target.decode(hypothesis)
        result["cases"].append({"id": case["id"], "source": "en", "target": "sw",
                                "protocol_sha256": case["protocol_sha256"], "original": case["text"],
                                "preprocessed": normalized, "translation": output,
                                "input_tokens": len(encoded), "output_tokens": len(hypothesis),
                                "hit_decode_cap": len(hypothesis) >= 256,
                                "score": decoded.scores[0],
                                "decode_ms": (time.perf_counter()-before_decode)*1000,
                                "total_ms": (time.perf_counter()-began)*1000})
        if (index + 1) % 20 == 0:
            save()
            print(json.dumps({"completed": index+1, "elapsed_seconds": result["elapsed_seconds"],
                              "rss_kib": result["peak_process_rss_kib"]}), flush=True)
        if time.perf_counter()-start > 1200:
            save()
            raise SystemExit("bounded 20-minute capture time exhausted; partial retained")
    result["complete"] = True
    values = sorted(r["total_ms"] for r in result["cases"])
    result["latency_summary"] = {"median_ms": statistics.median(values),
                                 "p95_ms": values[int(.95*(len(values)-1))], "max_ms": max(values)}
    save()
    print(json.dumps({k:result[k] for k in ("complete", "load_ms", "elapsed_seconds", "peak_process_rss_kib", "latency_summary")}))


if __name__ == "__main__":
    main()
