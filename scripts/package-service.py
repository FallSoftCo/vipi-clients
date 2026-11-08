#!/usr/bin/env python3
"""Package committed backend/ops source on an authorized Linux build workspace.

The retired OZZZ hosts are not build targets. Use CPython 3.12/x86_64 matching
the consolidated production runtime; the output is private service source.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import socket
import platform
import subprocess
import sys
import tarfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--revision", default="HEAD")
parser.add_argument("--output", type=Path)
args = parser.parse_args()
assert platform.system() == "Linux" and platform.machine() == "x86_64"
assert sys.version_info[:2] == (3, 12), "Use the qualified CPython 3.12 environment"
assert socket.gethostname() not in {"ozzz-aosp", "ozzz-gpu"}, "Retired build host"
root = Path(__file__).resolve().parents[1]
assert not subprocess.check_output(["git", "status", "--porcelain", "--", "backend", "ops"], cwd=root), "Commit backend/ops changes first"
revision = subprocess.check_output(["git", "rev-parse", "--verify", args.revision + "^{commit}"], cwd=root, text=True).strip()
output = (args.output or root / "artifacts" / f"service-{revision[:12]}").resolve()
assert not output.exists()
output.mkdir(parents=True)
assert shutil.disk_usage(output).free >= 2 * 1024**3, "Need 2 GiB working headroom"
source = output / "source"; source.mkdir()
source_archive = output / "source.tar"
with source_archive.open("wb") as archive_file:
    subprocess.run(["git", "archive", "--format=tar", revision, "backend", "ops"], cwd=root, stdout=archive_file, check=True)
with tarfile.open(source_archive) as archive:
    archive.extractall(source, filter="data")
tree = output / "release"; tree.mkdir()
installer = ([shutil.which("uv"), "pip", "install", "--python", sys.executable] if shutil.which("uv")
             else [sys.executable, "-m", "pip", "install", "--no-compile"])
subprocess.run(installer + ["--only-binary=:all:", "--constraint", str(source / "backend/requirements.lock"),
    "--target", str(tree / "deps"), str(source / "backend")], check=True)
shutil.copytree(source / "backend/migrations", tree / "migrations", ignore=shutil.ignore_patterns("__pycache__"))
shutil.copy(source / "backend/alembic.ini", tree)
shutil.copytree(source / "ops", tree / "ops")
manifest = {"revision": revision, "python": sys.version, "machine": "x86_64", "build_host": socket.gethostname(),
    "source_archive_sha256": hashlib.sha256(source_archive.read_bytes()).hexdigest(),
    "dependencies": sorted([{"name": d.metadata["Name"], "version": d.version} for d in importlib.metadata.distributions(path=[str(tree / "deps")])], key=lambda d: d["name"]), "files": {}}
for path in sorted(tree.rglob("*")):
    if path.is_file():
        manifest["files"][str(path.relative_to(tree))] = hashlib.sha256(path.read_bytes()).hexdigest()
(tree / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
archive = output / "release.tar.gz"
with tarfile.open(archive, "w:gz") as tar:
    tar.add(tree, arcname=".")
summary = {"revision": revision, "archive": str(archive), "bytes": archive.stat().st_size,
    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "files": len(manifest["files"])}
(output / "receipt.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary))
