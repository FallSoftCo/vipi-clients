#!/usr/bin/env python3
"""Verify the committed live-reading data; never prepare translation catalogs."""

import hashlib
import json
from pathlib import Path


def verify(directory):
    provenance = json.loads(
        (directory / "chinese-ordinary.provenance.json").read_text()
    )
    if provenance["runtime_data"] != "chinese-ordinary.json":
        raise ValueError("Unexpected live-reading resource")
    data = (directory / "chinese-ordinary.json").read_bytes()
    if (
        len(data) != provenance["bytes"]
        or hashlib.sha256(data).hexdigest() != provenance["sha256"]
    ):
        raise ValueError("Live-reading data differs from its committed provenance")
    return {
        "verified": True,
        "resource": provenance["runtime_data"],
        "sha256": provenance["sha256"],
    }


if __name__ == "__main__":
    print(json.dumps(verify(Path(__file__).resolve().parents[1] / "data/readings")))
