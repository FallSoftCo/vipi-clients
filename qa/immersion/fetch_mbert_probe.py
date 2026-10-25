#!/usr/bin/env python3
"""Pinned research weights for the published mBERT layer-8 alignment baseline."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path("vendor-research/context-encoder/mbert-001")
REVISION = "3f076fdb1ab68d5b2880cb87a0886f315b8146f8"
FILES = {
    "README.md": (7104, "b665d060ca923acbbc1720f9318b2c792bf01b6f"),
    "config.json": (625, "b122e74db13b415ea824c074da33c1c44f0d13a3"),
    "model.safetensors": (714290682, "876f584f15ebf14887dec17539c114bb99a032e96b9e72507a51c41e205337fc"),
    "tokenizer.json": (1961828, "420b0fc31334c64ddf53cc3e9222a6d4c59d0cae"),
    "tokenizer_config.json": (49, "2ba5de7675473164e07f3b3531748c9a6f113a2c"),
    "vocab.txt": (995526, "e837bab60a5d204e29622d127c2dafe508aa0731"),
}
ROOT.mkdir(parents=True, exist_ok=False)
receipt = {"model": "google-bert/bert-base-multilingual-cased", "revision": REVISION,
           "license_declaration": "Apache-2.0 in the retained Hugging Face model card; Google BERT upstream",
           "purpose": "CPU research only; no app integration or redistribution", "files": {}}
for name, (size, expected) in FILES.items():
    url = f"https://huggingface.co/google-bert/bert-base-multilingual-cased/resolve/{REVISION}/{name}"
    target = ROOT / name; partial = target.with_name(target.name+".partial")
    sha256 = hashlib.sha256(); git = hashlib.sha1(f"blob {size}\0".encode()); count = 0
    with urllib.request.urlopen(url, timeout=120) as response, partial.open("xb") as output:
        while chunk := response.read(1024*1024):
            count += len(chunk)
            if count > size: raise ValueError("Download exceeds pinned size")
            output.write(chunk); sha256.update(chunk); git.update(chunk)
    assert count == size
    assert (sha256.hexdigest() if name == "model.safetensors" else git.hexdigest()) == expected
    partial.replace(target)
    receipt["files"][name] = {"size": size, "sha256": sha256.hexdigest(), "url": url}
    print(name, count, flush=True)
(ROOT / "receipt.json").write_text(json.dumps(receipt, indent=2)+"\n")
