#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, subprocess

ROOT = Path("/aosp/development/vipi")
OUT = ROOT / "artifacts/fast-align-toolchain-001"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


revision = subprocess.check_output(
    ["git", "-C", str(OUT / "source"), "rev-parse", "HEAD"], text=True
).strip()
assert revision == "cab1e9aac8d3bb02ff5ae58218d8d225a039fa11"
assert not (OUT / "receipt.json").exists()
assert (
    subprocess.check_output(
        ["git", "-C", str(OUT / "source"), "status", "--porcelain"], text=True
    )
    == ""
)
(OUT / "build").mkdir(exist_ok=False)
commands = []
for name, sources in [
    ("fast_align", ["fast_align.cc", "ttables.cc"]),
    ("atools", ["alignment_io.cc", "atools.cc"]),
]:
    command = [
        "c++",
        "-std=c++11",
        "-O3",
        "-Wall",
        "-I",
        str(OUT / "source"),
        *[str(OUT / "source/src" / s) for s in sources],
        "-o",
        str(OUT / "build" / name),
    ]
    subprocess.run(command, check=True, stdin=subprocess.DEVNULL)
    commands.append(command)
binaries = {
    p.name: dict(bytes=p.stat().st_size, sha256=sha(p))
    for p in [OUT / "build/fast_align", OUT / "build/atools"]
}
receipt = dict(
    complete=True,
    source="https://github.com/clab/fast_align",
    revision=revision,
    license_sha256=sha(OUT / "source/LICENSE.txt"),
    binaries=binaries,
    commands=commands,
    compiler=subprocess.check_output(["c++", "--version"], text=True).splitlines()[0],
    scope="Authoring experiment only; no app runtime integration or accuracy claim",
    driver_sha256=sha(Path(__file__)),
    build_note="Direct equivalent of upstream two executable targets; optional sparsehash/OpenMP not enabled.",
)
(OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
