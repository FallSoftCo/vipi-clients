#!/usr/bin/env python3
"""Build a complete immutable service dependency tree on OZZZ-OS, not the app
host. Both qualified hosts use Ubuntu 24.04 / CPython 3.12 / x86_64.
"""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tarfile

assert socket.gethostname() == "ozzz-aosp"
root = Path("/aosp/development/vipi")
assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=root), "Commit the release source first"
revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
output = root / "artifacts" / f"service-{revision[:12]}"
assert not output.exists()
output.mkdir()
tree = output / "release"; tree.mkdir()
subprocess.run([sys.executable, "-m", "pip", "install", "--only-binary=:all:", "--no-compile",
    "--constraint", str(root / "backend/requirements.lock"), "--target", str(tree / "deps"), str(root / "backend")], check=True)
shutil.copytree(root / "backend/migrations", tree / "migrations", ignore=shutil.ignore_patterns("__pycache__"))
shutil.copy(root / "backend/alembic.ini", tree)
shutil.copytree(root / "ops", tree / "ops")
manifest = {"revision": revision, "python": sys.version, "machine": "x86_64",
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
