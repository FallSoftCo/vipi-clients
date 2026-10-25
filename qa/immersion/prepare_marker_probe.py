#!/usr/bin/env python3
"""Freeze an exploratory black-box translation correspondence probe.

Related research uses translation perturbations for quality estimation:
https://aclanthology.org/2023.mtsummit-research.6/
This exact two-marker experiment is our own hypothesis, not a reproduction.
The independently authored target terms are evaluation-only, never inputs to MT.
"""
import json
from pathlib import Path
from context_token_pilot import GOLD

root = Path(__file__).resolve().parents[2]
corpus = json.loads((root / "qa/immersion/corpus.json").read_text())
native = json.loads((root / "artifacts/context-android-authored-001.json").read_text())
samples = []
for pair in native["results"]:
    for sample in pair["samples"]:
        if sample["id"] not in GOLD: continue
        for concept, terms in GOLD[sample["id"]].items():
            source = sample["original"]; term = terms[pair["source"]]
            assert source.count(term) == 1
            start = source.index(term); end = start + len(term)
            words = [w for w in sample["source_words"] if w["start"] < end and w["end"] > start]
            assert len(words) == 1
            word = words[0]
            assert source[word["start"]:word["end"]] == word["text"]
            samples.append({"case": sample["id"], "concept": concept, "source": pair["source"], "target": pair["target"],
                            "original": source, "start": word["start"], "end": word["end"], "source_word": word["text"],
                            "expected_target": terms[pair["target"]]})
assert len(samples) == 360
protocol = {"schema": 1, "scope": "Reused 360 easy authored correspondences, not linguistic acceptance",
            "method": "Replace native source word separately with each marker; require one preserved marker and exactly identical exterior text in baseline and both perturbed translations; replacement must cover complete native target words",
            "markers": ["ZXQ9129", "QXZ7281"], "threshold_fitted": False, "samples": samples}
out = root / "artifacts/context-marker-protocol-001.json"
with out.open("x") as f: json.dump(protocol, f, ensure_ascii=False, indent=2); f.write("\n")
print(out)
