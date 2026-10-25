#!/usr/bin/env python3
"""Pinned third-party mirror of AWESOME alignment weights; research only.

The upstream no-consistency checkpoint link returned HTTP 404 on 2026-10-25.
This mirror declares the consistency-trained checkpoint. Its relationship to
the upstream archive has not been independently byte-verified. Do not ship it
on the strength of this download or the small development probe.
"""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path("vendor-research/context-encoder/awesome-co-001")
REVISION = "777756717e1fa9556e304d4d5db173ee386b9c16"
FILES = {
    "README.md": (3170, "5db147e52e3abacf1eb420bf067212961c9cb962"),
    "config.json": (1190, "eca194c5d79b385ec8d6109a1605a4b4686ee308"),
    "pytorch_model.bin": (1086292375, "9f9d19adbab07c9f5ec2d74fe5701a66c123919feb35d05fce29969b6a85adb9"),
    "special_tokens_map.json": (112, "e7b0375001f109a6b8873d756ad4f7bbb15fbaa5"),
    "tokenizer_config.json": (40, "9de0d36b30e859708df4d608b6f6b6d8f48e3243"),
    "vocab.txt": (995526, "e837bab60a5d204e29622d127c2dafe508aa0731"),
}
ROOT.mkdir(parents=True, exist_ok=False)
receipt = {"model": "aneuraz/awesome-align-with-co", "revision": REVISION,
           "license_declaration": "BSD-3-Clause in mirror model card; upstream includes Apache-2.0 components",
           "upstream": "https://github.com/neulab/awesome-align/tree/5f150d45bbe51e167daf0a84abebaeb07c3323d1",
           "provenance_limit": "Third-party checkpoint mirror; no upstream archive byte comparison",
           "purpose": "CPU research only; no app integration or redistribution", "files": {}}
for name, (size, expected) in FILES.items():
    url = f"https://huggingface.co/aneuraz/awesome-align-with-co/resolve/{REVISION}/{name}"
    target = ROOT / name; partial = target.with_name(target.name + ".partial")
    sha256 = hashlib.sha256(); git = hashlib.sha1(f"blob {size}\0".encode()); count = 0
    with urllib.request.urlopen(url, timeout=120) as response, partial.open("xb") as output:
        while chunk := response.read(1024 * 1024):
            count += len(chunk)
            if count > size: raise ValueError("Download exceeds pinned size")
            output.write(chunk); sha256.update(chunk); git.update(chunk)
    assert count == size
    assert (sha256.hexdigest() if name.endswith(".bin") else git.hexdigest()) == expected
    partial.replace(target)
    receipt["files"][name] = {"size": size, "sha256": sha256.hexdigest(), "url": url}
    print(name, count, flush=True)
(ROOT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
