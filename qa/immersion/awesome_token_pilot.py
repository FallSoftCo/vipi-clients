#!/usr/bin/env python3
"""Bounded AWESOME subword-alignment development probe, not acceptance.

Uses the published per-word tokenization, raw layer-8 dot product, bidirectional
softmax intersection at 1e-3, then maps subwords back to native words. The Vipi
selection rule requires a single target and single reverse source at word level.
Native segmentation and this last filter differ from published benchmarks.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

import numpy as np
import torch
from transformers import BertModel, BertTokenizer
from context_token_pilot import GOLD


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main(args):
    args.output.mkdir(parents=True, exist_ok=False)
    corpus = json.loads(args.corpus.read_text())
    native = json.loads(args.native.read_text())
    texts = {c["id"]: c["text"] for c in corpus["cases"] if c["id"] in GOLD}
    words = {}
    for pair in native["results"]:
        for sample in pair["samples"]:
            if sample["id"] not in GOLD: continue
            key = sample["id"], pair["source"]
            assert sample["original"] == texts[key[0]][key[1]]
            assert all(sample["original"][w["start"]:w["end"]] == w["text"] for w in sample["source_words"])
            if key in words: assert words[key] == sample["source_words"]
            words[key] = sample["source_words"]
    protocol = {"schema": 1, "backend": "awesome-co-001", "gold": GOLD,
                "alignment": "native words independently WordPiece tokenized; raw layer-8 dot; bidirectional softmax > 0.001 intersection; subword links unioned to words",
                "selection": "exactly one aligned target word and exactly one reverse source word; no fitted threshold",
                "criterion": "selected native target word overlaps authored gold substring; not exact replacement span correctness",
                "scope": "360 authored correspondences, 90 directions, two scenarios; reused development probe, not untouched acceptance",
                "method_reference": "https://github.com/neulab/awesome-align/tree/5f150d45bbe51e167daf0a84abebaeb07c3323d1",
                "weights_provenance": json.loads((args.model / "receipt.json").read_text()),
                "source_hashes": {str(p): digest(p) for p in [args.corpus, args.native, Path(__file__), *[args.model / p for p in ["pytorch_model.bin", "vocab.txt", "config.json"]]]}}
    raw = (json.dumps(protocol, ensure_ascii=False, indent=2) + "\n").encode()
    (args.output / "protocol.json").write_bytes(raw)
    torch.set_num_threads(2); torch.set_num_interop_threads(1)
    started = time.perf_counter()
    tokenizer = BertTokenizer.from_pretrained(args.model, local_files_only=True)
    model = BertModel.from_pretrained(args.model, local_files_only=True, weights_only=True,
                                     output_hidden_states=True, attn_implementation="eager").eval()
    load_ms = (time.perf_counter() - started) * 1000
    vectors = {}; maps = {}; timings = []
    for key, native_words in words.items():
        started = time.perf_counter()
        pieces = [tokenizer.encode(w["text"], add_special_tokens=False) for w in native_words]
        ids = [tokenizer.cls_token_id] + [i for group in pieces for i in group] + [tokenizer.sep_token_id]
        assert len(ids) <= 512 and all(pieces)
        with torch.inference_mode():
            output = model(input_ids=torch.tensor([ids])).hidden_states[8][0, 1:-1]
        vectors[key] = output
        maps[key] = [i for i, group in enumerate(pieces) for _ in group]
        timings.append((time.perf_counter() - started) * 1000)

    def gold_index(case, concept, language):
        sentence = texts[case][language]; term = GOLD[case][concept][language]
        assert sentence.count(term) == 1
        start = sentence.index(term); end = start + len(term)
        indices = [i for i, w in enumerate(words[case, language]) if w["start"] < end and w["end"] > start]
        assert len(indices) == 1
        return indices[0]

    observations = []
    for case, concepts in GOLD.items():
        for src in corpus["languages"]:
            for dst in corpus["languages"]:
                if src == dst: continue
                dot = vectors[case, src] @ vectors[case, dst].T
                mask = (dot.softmax(dim=-1) > .001) & (dot.softmax(dim=-2) > .001)
                links = {(maps[case, src][i], maps[case, dst][j]) for i, j in mask.nonzero().tolist()}
                for concept in concepts:
                    i = gold_index(case, concept, src); expected = gold_index(case, concept, dst)
                    candidates = sorted(j for a, j in links if a == i)
                    selected = len(candidates) == 1 and sum(j == candidates[0] for _, j in links) == 1
                    observations.append({"case": case, "concept": concept, "source": src, "target": dst,
                                         "source_word": words[case, src][i]["text"], "expected_target": words[case, dst][expected]["text"],
                                         "aligned_targets": [words[case, dst][j]["text"] for j in candidates],
                                         "expected_aligned": expected in candidates, "selected": selected,
                                         "selected_correct": selected and candidates == [expected]})
    report = {"protocol_sha256": hashlib.sha256(raw).hexdigest(), "cases": len(observations),
              "expected_aligned": sum(o["expected_aligned"] for o in observations),
              "selected": sum(o["selected"] for o in observations),
              "selected_wrong": sum(o["selected"] and not o["selected_correct"] for o in observations),
              "load_ms": load_ms, "sentence_p50_ms": float(np.median(timings)), "sentence_p95_ms": float(np.percentile(timings, 95)),
              "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "platform": "OZZZ-OS x86 CPU, two threads; not mobile", "linguistic_acceptance": False,
              "translation_faithfulness_tested": False, "observations": observations}
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k:v for k,v in report.items() if k != "observations"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["corpus", "native", "model", "output"]: parser.add_argument("--" + name, type=Path, required=True)
    main(parser.parse_args())
