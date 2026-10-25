#!/usr/bin/env python3
"""Pinned public translation weights for a bounded CPU comparison, not shipping."""
import hashlib
import json
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_url
import requests

repository = "facebook/m2m100_418M"
root = Path("vendor-research/m2m100-001")
root.mkdir(parents=True, exist_ok=False)
info = HfApi().model_info(repository, files_metadata=True)
assert info.card_data.get("license") == "mit"
selected = {"README.md", "config.json", "generation_config.json", "pytorch_model.bin",
            "sentencepiece.bpe.model", "special_tokens_map.json", "tokenizer_config.json", "vocab.json"}
files = [f for f in info.siblings if f.rfilename in selected]
assert {f.rfilename for f in files} == selected
receipt = {"repository": repository, "revision": info.sha, "license_metadata": "mit",
           "purpose": "CPU comparison only; no app integration or redistribution", "files": {}}
(root / "intent.json").write_text(json.dumps(receipt, indent=2) + "\n")
for item in files:
    url = hf_hub_url(repository, item.rfilename, revision=info.sha)
    digest = hashlib.sha256(); size = 0
    temporary = root / (item.rfilename + ".part")
    with requests.get(url, stream=True, timeout=(30, 120)) as response:
        response.raise_for_status()
        with temporary.open("xb") as output:
            for block in response.iter_content(1024 * 1024):
                output.write(block); digest.update(block); size += len(block)
    assert size == item.size, item.rfilename
    if item.lfs:
        assert digest.hexdigest() == item.lfs.sha256, item.rfilename
    temporary.rename(root / item.rfilename)
    receipt["files"][item.rfilename] = {"bytes": size, "sha256": digest.hexdigest()}
    (root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(item.rfilename, size, flush=True)
