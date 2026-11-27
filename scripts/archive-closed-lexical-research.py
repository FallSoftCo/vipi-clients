#!/usr/bin/env python3
"""One-shot verified archival of closed comparison-model assets, 2026-10-27.

Keep original consumer paths through the existing read-only development mount.
This moves public research weights, not code, services, dictionaries or models
used by the native apps. No stopped research job is resumed.
"""

from pathlib import Path
import hashlib
import json
import os
import shlex
import subprocess
import time

ROOT = Path("/aosp/development/vipi")
MOUNT = Path("/aosp/storage/dev-workspaces")
REL = "vipi/20261027-closed-research-001"
REMOTE = "u684605@u684605.your-storagebox.de"
SSH = [
    "ssh",
    "-p",
    "23",
    "-i",
    "/home/aosp/.ssh/8bar-render-archive_ed25519",
    "-o",
    "UserKnownHostsFile=/home/aosp/.ssh/8bar-render-archive_known_hosts",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "IdentitiesOnly=yes",
    "-o",
    "BatchMode=yes",
]
FILES = [
    "context-encoder/e5-small-001/onnx/model_qint8_avx512_vnni.onnx",
    "context-encoder/awesome-co-001/pytorch_model.bin",
    "context-encoder/mbert-001/model.safetensors",
    "m2m100-001/pytorch_model.bin",
]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def idle(path):
    result = subprocess.run(["fuser", str(path)], capture_output=True)
    if result.returncode != 1:
        raise ValueError("Asset has an active/open consumer: " + str(path))


def main():
    if subprocess.check_output(["hostname"], text=True).strip() != "ozzz-aosp":
        raise ValueError("Wrong host")
    assert os.geteuid() == 0 and os.path.ismount(MOUNT)
    output = ROOT / "artifacts/closed-research-archive-001"
    output.mkdir(exist_ok=False)
    receipt = dict(
        schema="vipi-closed-research-archive-1",
        owner="01a16e0d-ac69-7dd0-872a-8cf087160515",
        source_retained=True,
        original_paths_preserved=True,
        archive_root=str(MOUNT / REL),
        files=[],
        complete=False,
    )

    def save():
        temporary = output / "receipt.tmp"
        temporary.write_text(json.dumps(receipt, indent=2) + "\n")
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        temporary.replace(output / "receipt.json")

    save()
    for relative in FILES:
        source = ROOT / "vendor-research" / relative
        destination = MOUNT / REL / relative
        assert source.is_file() and not source.is_symlink() and not destination.exists()
        idle(source)
        before = source.stat()
        checksum = digest(source)
        parent = "dev-workspaces/" + REL + "/" + str(Path(relative).parent)
        subprocess.run(SSH + [REMOTE, "mkdir -p " + shlex.quote(parent)], check=True)
        subprocess.run(
            [
                "rsync",
                "-a",
                "--no-owner",
                "--no-group",
                "--protect-args",
                "-e",
                shlex.join(SSH),
                str(source),
                REMOTE + ":dev-workspaces/" + REL + "/" + relative,
            ],
            check=True,
        )
        assert destination.is_file() and destination.stat().st_size == before.st_size
        assert digest(destination) == checksum
        idle(source)
        after = source.stat()
        assert (before.st_ino, before.st_size, before.st_mtime_ns) == (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        row = dict(
            source=str(source),
            destination=str(destination),
            bytes=before.st_size,
            sha256=checksum,
            verified=True,
            consumer_link_installed=False,
        )
        receipt["files"].append(row)
        save()
        temporary = source.with_name(source.name + ".verified-remote")
        temporary.symlink_to(destination)
        temporary.replace(source)
        directory = os.open(source.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        assert source.is_symlink() and source.stat().st_size == before.st_size
        row["consumer_link_installed"] = True
        save()
        print(json.dumps(row), flush=True)
    # The rejected converted comparison binary is regenerated from the retained
    # original if ever needed. Retain configuration, provenance and QA reports.
    converted = ROOT / "vendor-research/m2m100-001/ct2-int8/model.bin"
    idle(converted)
    receipt["retired_derived_output"] = dict(
        path=str(converted),
        bytes=converted.stat().st_size,
        sha256=digest(converted),
        original_sha256=receipt["files"][-1]["sha256"],
        reason="Rejected comparison conversion; source weights and conversion metadata retained.",
    )
    save()
    converted.unlink()
    receipt["complete"] = True
    receipt["finished_at"] = time.time()
    save()
    print(
        json.dumps(
            {
                "complete": True,
                "archived_bytes": sum(r["bytes"] for r in receipt["files"]),
                "retired_derived_bytes": receipt["retired_derived_output"]["bytes"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
