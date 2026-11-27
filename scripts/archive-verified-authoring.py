#!/usr/bin/env python3
"""Preserve a closed Vipi authoring artifact on the existing Storage Box.

Requires a completed producer receipt with the exact artifact digest. Original
paths remain usable through verified links. Never archives a live consumer.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time

ROOT = Path("/aosp/development/vipi")
MOUNT = Path("/aosp/storage/dev-workspaces")
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


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def idle(path):
    result = subprocess.run(["fuser", str(path)], capture_output=True)
    if result.returncode != 1:
        raise ValueError("Artifact has an open consumer: " + str(path))
    for suffix in ("-wal", "-journal", "-shm"):
        assert not Path(str(path) + suffix).exists(), "SQLite sidecar exists"


def remote_digest(destination):
    # Hash on the storage endpoint; do not download multi-GB files to hash them.
    relative = "dev-workspaces/" + str(destination.relative_to(MOUNT))
    result = subprocess.check_output(
        SSH + [REMOTE, "sha256sum " + shlex.quote(relative)], text=True
    )
    checksum, name = result.strip().split(None, 1)
    assert name == relative and re.fullmatch("[a-f0-9]{64}", checksum)
    return checksum


def main(args):
    assert os.geteuid() == 0 and os.path.ismount(MOUNT)
    assert subprocess.check_output(["hostname"], text=True).strip() == "ozzz-aosp"
    assert re.fullmatch(r"[a-z0-9-]+", args.revision)
    relative = Path(args.artifact)
    assert not relative.is_absolute() and len(relative.parts) == 2
    assert all(
        re.fullmatch(r"[a-zA-Z0-9_.-]+", p) and p not in (".", "..")
        for p in relative.parts
    )
    source = ROOT / "artifacts" / relative
    producer_path = source.parent / "receipt.json"
    producer = json.loads(producer_path.read_text())
    assert producer[args.completion_key] is True and re.fullmatch(
        "[a-f0-9]{64}", producer[args.digest_key]
    )
    expected = producer[args.digest_key]
    archive = "vipi/" + args.revision
    destination = MOUNT / archive / relative
    output = ROOT / "artifacts" / ("archive-" + args.revision)
    output.mkdir(exist_ok=True)
    receipt_path = output / "receipt.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        assert receipt["source"] == str(source) and receipt["destination"] == str(
            destination
        )
        assert receipt["sha256"] == expected and receipt["owner"] == args.owner
        assert receipt["producer_receipt_sha256"] == digest(producer_path)
        if receipt["complete"]:
            assert source.is_symlink() and source.resolve() == destination.resolve()
            assert remote_digest(destination) == expected
            print(
                json.dumps(
                    dict(
                        complete=True,
                        already_archived=True,
                        bytes=destination.stat().st_size,
                    )
                )
            )
            return
    else:
        assert source.is_file() and not source.is_symlink()
        receipt = dict(
            schema="vipi-verified-authoring-archive-1",
            source=str(source),
            destination=str(destination),
            sha256=expected,
            bytes=source.stat().st_size,
            owner=args.owner,
            producer_receipt_sha256=digest(producer_path),
            archiver_sha256=digest(Path(__file__)),
            verification="source digest plus storage-endpoint digest and mounted size",
            source_retained=True,
            original_path_preserved=True,
            complete=False,
        )

    def save():
        temporary = output / "receipt.tmp"
        temporary.write_text(json.dumps(receipt, indent=2) + "\n")
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        temporary.replace(receipt_path)

    save()
    if not source.is_symlink():
        idle(source)
        before = source.stat()
        assert before.st_nlink == 1 and digest(source) == expected
        if not destination.exists():
            remote = "dev-workspaces/" + archive + "/" + str(relative)
            subprocess.run(
                SSH + [REMOTE, "mkdir -p " + shlex.quote(str(Path(remote).parent))],
                check=True,
            )
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
                    REMOTE + ":" + remote,
                ],
                check=True,
            )
        assert destination.is_file() and destination.stat().st_size == before.st_size
        assert remote_digest(destination) == expected
        idle(source)
        after = source.stat()
        assert (before.st_ino, before.st_size, before.st_mtime_ns) == (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        receipt["verified_copy"] = True
        save()
        temporary = source.with_name(source.name + ".verified-remote")
        assert not temporary.exists() and not temporary.is_symlink()
        temporary.symlink_to(destination)
        temporary.replace(source)
        directory = os.open(source.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    assert source.is_symlink() and source.resolve() == destination.resolve()
    assert (
        source.stat().st_size == receipt["bytes"]
        and remote_digest(destination) == expected
    )
    receipt.update(complete=True, finished_at=time.time())
    save()
    print(
        json.dumps(
            dict(complete=True, archived_bytes=receipt["bytes"], source=str(source))
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--digest-key", default="sha256")
    parser.add_argument(
        "--completion-key",
        choices=["complete", "complete_source_scan"],
        default="complete",
    )
    parser.add_argument("--revision", required=True)
    parser.add_argument("--owner", required=True)
    main(parser.parse_args())
