#!/usr/bin/env python3
"""Correct present witness endpoints without repeating the completed corpus scan."""

from pathlib import Path
import hashlib, json, shutil, subprocess, time

R = Path("/aosp/development/vipi")
OUT = R / "artifacts/present-witness-revision-002"
SNAP = OUT / "compiler-source"


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def write(p, v):
    p.write_text(json.dumps(v, indent=2) + "\n")


OUT.mkdir(exist_ok=False)
SNAP.mkdir()
files = []
for p in sorted((R / "language-packs").glob("*.py")):
    dst = SNAP / p.name
    shutil.copy2(p, dst)
    files.append(dict(path=p.name, sha256=sha(dst)))
write(SNAP / "receipt.json", dict(files=files))
write(
    OUT / "plan.json",
    dict(
        complete=False,
        source_contexts="present-pilot-001",
        compiler_snapshot_sha256=sha(SNAP / "receipt.json"),
        prior_witness_accepted=False,
        correction="Do not classify an opposite endpoint as present merely because its spelling has a present dictionary form. Reapply finite-clause, noun-context and cross-lexeme past checks before canonicalizing. Keep nonpresent endpoints as competing evidence.",
        corpus_scan_repeated=False,
        production_promoted=False,
    ),
)
deadline = time.monotonic() + 7200
for name in ["tatoeba", "pgv", "massive"]:
    receipt = (
        R
        / "artifacts"
        / ("lexical-contexts-present-pilot-001-" + name)
        / "receipt.json"
    )
    while not receipt.exists():
        assert time.monotonic() < deadline, "Source context completion deadline reached"
        time.sleep(5)
    assert json.loads(receipt.read_text())["complete"]
# Avoid duplicating the original active witness compiler. Its unaccepted output
# is retained for provenance; the corrected endpoint rules define this revision.
prior = R / "artifacts/present-verb-context-pilot-001/receipt.json"
while not prior.exists():
    assert time.monotonic() < deadline, (
        "Original evaluation completion deadline reached"
    )
    time.sleep(5)
assert json.loads(prior.read_text())["complete"]
command = [
    str(R / ".venv-lexical-context/bin/python"),
    str(SNAP / "build_context_witnesses.py"),
    "--contexts",
    str(R / "artifacts/lexical-contexts-present-pilot-001-tatoeba/contexts.sqlite"),
    "--additional-context",
    str(R / "artifacts/lexical-contexts-present-pilot-001-pgv/contexts.sqlite"),
    "--additional-corpus-receipt",
    str(R / "artifacts/parallel-global-voices-001/receipt.json"),
    "--extra-context",
    str(R / "artifacts/lexical-contexts-present-pilot-001-massive/contexts.sqlite"),
    "--extra-corpus-receipt",
    str(R / "artifacts/massive-corpus-003/receipt.json"),
    "--source-exclusions",
    str(R / "artifacts/corpus-exclusions-001/hashes.sqlite"),
    "--output",
    str(R / "artifacts/context-witnesses-present-pilot-002"),
    "--pair",
    "en-es",
    "--pair",
    "es-en",
]
with (OUT / "build.log").open("x") as log:
    subprocess.run(
        ["storage-build", "--peak-bytes", str(2 * 1024**3), "--", *command],
        cwd=R,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        check=True,
    )
receipt = R / "artifacts/context-witnesses-present-pilot-002/receipt.json"
v = json.loads(receipt.read_text())
assert v["complete"]
write(
    OUT / "receipt.json",
    dict(
        complete=True,
        witness_receipt_sha256=sha(receipt),
        counts=v["counts"],
        source_contexts_reused=True,
        prior_witness_accepted=False,
        native_qualified=False,
        production_promoted=False,
    ),
)
print(json.dumps(dict(complete=True, counts=v["counts"])), flush=True)
