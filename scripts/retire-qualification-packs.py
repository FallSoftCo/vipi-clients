#!/usr/bin/env python3
"""Retire explicitly superseded compiled QA databases, retaining signed metadata.

The pinned upstream dictionary/catalog and replacement remain untouched. An
immutable receipt records hashes, replacement, open-file check and deletion.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def verify(directory):
    receipt = json.loads((directory / "receipt.json").read_text())
    assert receipt["qualification_only_key"] and receipt["private_key_written"] is False
    pairs = receipt["pairs"]
    assert len(pairs) == 90
    files = []
    for expected in pairs:
        pair = expected["pack_id"]
        assert len(pair) == 5 and pair[2] == "-" and pair.replace("-", "").isalpha()
        folder = directory / pair
        manifest = json.loads((folder / "manifest.json").read_text())
        assert manifest == expected
        path = folder / "vocabulary.sqlite"
        assert path.is_file() and not path.is_symlink()
        assert (
            path.stat().st_size == expected["bytes"]
            and digest(path) == expected["sha256"]
        )
        files.append(
            {
                "path": str(path.resolve()),
                "bytes": expected["bytes"],
                "sha256": expected["sha256"],
            }
        )
    return receipt, files


def main(args):
    assert not args.receipt.exists(), "Preserve previous retirement receipts"
    replacement, _ = verify(args.replacement)
    retired = []
    for directory in args.superseded:
        assert directory.resolve() != args.replacement.resolve()
        receipt, files = verify(directory)
        assert receipt["catalog_sha256"] == replacement["catalog_sha256"]
        assert max(p["revision"] for p in receipt["pairs"]) < min(
            p["revision"] for p in replacement["pairs"]
        )
        retired.extend(files)
    # This is a scoped current-use check, not a wildcard cleanup. A check error
    # cannot authorize removal. The operator supplies only superseded revisions.
    opened = subprocess.run(
        ["lsof", "-t", "--"] + [f["path"] for f in retired],
        text=True,
        capture_output=True,
    )
    assert opened.returncode == 1 and not opened.stdout.strip(), (
        "A selected database is open, or lsof failed"
    )
    assert not opened.stderr.strip(), opened.stderr
    plan = {
        "action": "retire_superseded_compiled_qualification_databases",
        "replacement": str(args.replacement.resolve()),
        "replacement_receipt_sha256": digest(args.replacement / "receipt.json"),
        "preserved": [
            "upstream dictionary",
            "sense catalog",
            "replacement databases",
            "all manifests/signatures/public keys",
            "test and provenance receipts",
        ],
        "files": retired,
        "bytes": sum(f["bytes"] for f in retired),
        "completed": False,
    }
    args.receipt.write_text(json.dumps(plan, indent=2) + "\n")
    for file in retired:
        path = Path(file["path"])
        assert path.stat().st_size == file["bytes"]
        path.unlink()
    plan["completed"] = True
    args.receipt.write_text(json.dumps(plan, indent=2) + "\n")
    print(
        json.dumps(
            {"completed": True, "databases": len(retired), "bytes": plan["bytes"]}
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--superseded", type=Path, action="append", required=True)
    parser.add_argument("--replacement", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    main(parser.parse_args())
