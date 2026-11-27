#!/usr/bin/env python3
"""Compile bounded whole-noun context alternatives after the pinned observation pass."""

from pathlib import Path
import hashlib, json, shutil, subprocess, time

R = Path("/aosp/development/vipi")
OUT = R / "artifacts/noun-alternatives-001"
SNAP = OUT / "compiler-source"


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def save(p, v):
    p.write_text(json.dumps(v, indent=2) + "\n")


OUT.mkdir(exist_ok=False)
SNAP.mkdir()
files = []
for p in sorted((R / "language-packs").glob("*.py")):
    d = SNAP / p.name
    shutil.copy2(p, d)
    files.append(dict(path=p.name, sha256=sha(d)))
save(SNAP / "receipt.json", dict(files=files))
save(
    OUT / "plan.json",
    dict(
        owner="01a16e0d-ac69-7dd0-872a-8cf087160515",
        compiler_snapshot_sha256=sha(SNAP / "receipt.json"),
        observations="noun-observations-001",
        base="context-witnesses-504",
        output="context-witnesses-506",
        peak_bytes=1024**3,
        admission_basis="117,338,112-byte base plus noun alternative rows and examples. Prior 3.74m present observations added 54.3 MB; 48.63m observations is the unfiltered upper bound for this smaller noun subset, giving under 824 MB at that measured density; 1 GiB covers SQLite journals and indexes.",
        production_promoted=False,
    ),
)
receipt = R / "artifacts/noun-observations-001/receipt.json"
deadline = time.monotonic() + 7200
while not receipt.exists():
    assert time.monotonic() < deadline, "Observation completion deadline reached"
    time.sleep(10)
assert json.loads(receipt.read_text())["complete"]
with (OUT / "build.log").open("x") as log:
    subprocess.run(
        [
            "storage-build",
            "--peak-bytes",
            str(1024**3),
            "--",
            str(R / ".venv-lexical-context/bin/python"),
            str(SNAP / "build_semantic_alternatives.py"),
            "--kind",
            "noun",
            "--observations",
            str(receipt.with_name("observations.sqlite")),
            "--dictionary",
            str(R / "artifacts/lexical-present-verbs-001/catalog.json"),
            "--base",
            str(R / "artifacts/context-witnesses-504/witnesses.sqlite"),
            "--output",
            str(R / "artifacts/context-witnesses-506"),
        ],
        cwd=R,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        check=True,
    )
result = R / "artifacts/context-witnesses-506/receipt.json"
v = json.loads(result.read_text())
assert v["complete"]
save(
    OUT / "receipt.json",
    dict(
        complete=True,
        result_receipt_sha256=sha(result),
        observations_receipt_sha256=sha(receipt),
        counts=v["counts"],
        native_qualified=False,
        production_promoted=False,
    ),
)
print(json.dumps(dict(complete=True, counts=v["counts"])), flush=True)
