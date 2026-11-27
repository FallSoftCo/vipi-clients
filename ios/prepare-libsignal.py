#!/usr/bin/env python3
"""Verify the pinned vendor, or explicitly fetch missing public dependencies.

Never replaces an existing checkout or mismatching archive. Does not build,
install a toolchain, modify local source, or touch a simulator.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

COMMIT = "4beb029d8a941f81e7d9c6d8af1ed25a677569a8"
ARCHIVE = "libsignal-client-ios-build-v0.105.0.tar.gz"
ARCHIVE_SHA = "556a82414b545490085a0e21d94990788bdcbee4d769043f7889397872443faf"
ARCHIVE_BYTES = 178619863
LIBRARIES = {
    "target/aarch64-apple-ios/release/libsignal_ffi.a": (
        204350664,
        "296840c5af0ca4c2bccd638d19d19741d3f3433221846cd64eaa13100e0bacd2",
    ),
    "target/aarch64-apple-ios-sim/release/libsignal_ffi.a": (
        241411488,
        "6b1fc5f32ea114d9b01a761fb2c6ee26c741412a4b535b972825b4f0781a15c0",
    ),
}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify(path, size, sha):
    if not path.is_file() or path.stat().st_size != size or digest(path) != sha:
        raise RuntimeError("Missing or mismatching pinned dependency: " + str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Fetch only absent public source/artifacts after external host capacity admission",
    )
    parser.add_argument(
        "--vendor-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "vendor/libsignal",
    )
    args = parser.parse_args()
    root = args.vendor_root
    source = root / "source"
    if args.fetch:
        root.mkdir(parents=True, exist_ok=True)
        # Guest capacity is necessary; the VM controller's physical free space
        # must also be checked by the operator before requesting this action.
        required = (
            1024**3
            + ARCHIVE_BYTES
            + sum(v[0] for v in LIBRARIES.values())
            + 512 * 1024**2
        )
        if shutil.disk_usage(root).free < required:
            raise RuntimeError("Insufficient disk margin for vendor preparation")
    if not source.exists():
        if not args.fetch:
            raise RuntimeError(
                "Pinned libsignal source is absent; see CLIENT_SOURCE.md"
            )
        with tempfile.TemporaryDirectory(
            prefix="libsignal-source-", dir=root
        ) as staging:
            path = Path(staging) / "source"
            subprocess.run(["git", "init", str(path)], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(path),
                    "fetch",
                    "--depth",
                    "1",
                    "https://github.com/signalapp/libsignal.git",
                    COMMIT,
                ],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(path), "checkout", "--detach", COMMIT], check=True
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(path),
                    "submodule",
                    "update",
                    "--init",
                    "--recursive",
                ],
                check=True,
            )
            path.rename(source)
    head = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != COMMIT:
        raise RuntimeError(
            "Existing source has a different HEAD; preserve it and reconcile ownership"
        )
    dirty = subprocess.check_output(
        ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=normal"],
        text=True,
    ).splitlines()
    # Xcode resolves the documentation plugin without changing libsignal code.
    if any(line[3:] != "swift/Package.resolved" for line in dirty):
        raise RuntimeError(
            "Existing libsignal source edits require explicit reconciliation"
        )
    missing = [name for name in LIBRARIES if not (root / name).exists()]
    if missing and args.fetch:
        archive = root / ARCHIVE
        if not archive.exists():
            with tempfile.NamedTemporaryFile(
                prefix="libsignal-download-", dir=root, delete=False
            ) as target:
                temporary = Path(target.name)
                try:
                    url = "https://build-artifacts.signal.org/libraries/" + ARCHIVE
                    with urllib.request.urlopen(url, timeout=60) as response:
                        count = 0
                        for block in iter(lambda: response.read(1024 * 1024), b""):
                            count += len(block)
                            if count > ARCHIVE_BYTES:
                                raise RuntimeError("Artifact exceeds pinned size")
                            target.write(block)
                    target.flush()
                    verify(temporary, ARCHIVE_BYTES, ARCHIVE_SHA)
                    temporary.rename(archive)
                finally:
                    temporary.unlink(missing_ok=True)
        verify(archive, ARCHIVE_BYTES, ARCHIVE_SHA)
        with tarfile.open(archive, "r:gz") as bundle:
            for name in missing:
                member = bundle.getmember(name)
                size, sha = LIBRARIES[name]
                if not member.isfile() or member.size != size:
                    raise RuntimeError("Unexpected archive member")
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_suffix(".verified-download")
                if temporary.exists():
                    raise RuntimeError(
                        "Reconcile an earlier incomplete extraction: " + str(temporary)
                    )
                try:
                    with (
                        bundle.extractfile(member) as incoming,
                        temporary.open("xb") as target,
                    ):
                        shutil.copyfileobj(incoming, target, 1024 * 1024)
                    verify(temporary, size, sha)
                    if destination.exists():
                        raise RuntimeError(
                            "Destination appeared during preparation; preserve it"
                        )
                    temporary.rename(destination)
                finally:
                    temporary.unlink(missing_ok=True)
    for name, (size, sha) in LIBRARIES.items():
        verify(root / name, size, sha)
    print(
        json.dumps(
            {
                "verified": True,
                "source_commit": head,
                "artifacts": {name: sha for name, (_, sha) in LIBRARIES.items()},
            }
        )
    )


if __name__ == "__main__":
    main()
