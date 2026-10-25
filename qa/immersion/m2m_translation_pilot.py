#!/usr/bin/env python3
"""Bounded local CPU translation comparison; no release-quality approval."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

import ctranslate2
from transformers import AutoTokenizer

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--model", type=Path, required=True)
p.add_argument("--corpus", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
corpus = json.loads(a.corpus.read_bytes())
def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()
protocol = {"scope": "540 reused development messages; not held-out acceptance",
            "provider": "facebook/m2m100_418M", "runtime": ctranslate2.__version__,
            "runtime_platform": "OZZZ-OS CPU; not mobile", "compute_type": "int8",
            "inter_threads": 1, "intra_threads": 2, "beam_size": 4, "max_decoding_length": 256,
            "source_revision": json.loads((a.model / "receipt.json").read_text())["revision"],
            "hashes": {str(f): sha(f) for f in [Path(__file__), a.corpus, a.model / "receipt.json",
                                                     *sorted((a.model / "ct2-int8").glob("*"))]},
            "linguistic_acceptance": False, "app_integration": False}
(a.output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
start = time.perf_counter()
translator = ctranslate2.Translator(str(a.model / "ct2-int8"), device="cpu", compute_type="int8", inter_threads=1, intra_threads=2)
tokenizer = AutoTokenizer.from_pretrained(str(a.model), local_files_only=True)
rows = []
report = {"provider": protocol["provider"], "platform": protocol["runtime_platform"],
          "evidence": "actual_local_cpu_translation_not_mobile_or_linguistic_acceptance",
          "load_ms": (time.perf_counter() - start) * 1000, "results": rows, "finished": False}
for source in corpus["languages"]:
    tokenizer.src_lang = source
    for target in corpus["languages"]:
        if source == target:
            continue
        samples = []
        for case in corpus["cases"]:
            original = case["text"][source]
            tokens = tokenizer.convert_ids_to_tokens(tokenizer.encode(original))
            assert len(tokens) < 512, "Do not silently truncate source context"
            prefix = tokenizer.lang_code_to_token[target]
            started = time.perf_counter()
            result = translator.translate_batch([tokens], target_prefix=[[prefix]], beam_size=4,
                                                max_decoding_length=256, return_scores=True)[0]
            duration = (time.perf_counter() - started) * 1000
            generated = result.hypotheses[0]
            assert generated[0] == prefix
            text = tokenizer.decode(tokenizer.convert_tokens_to_ids(generated[1:]), skip_special_tokens=True)
            samples.append({"id": case["id"], "original": original, "translation": text,
                            "reference": case["text"][target], "latency_ms": duration,
                            "score": result.scores[0], "status": "executed" if text.strip() and len(generated) < 256 else "failed",
                            "generated_tokens": len(generated)})
        rows.append({"source": source, "target": target, "status": "executed", "samples": samples})
        report["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        temporary = a.output / "report.part"
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(a.output / "report.json")
        print(source, target, "complete", flush=True)
report["finished"] = True
(a.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
