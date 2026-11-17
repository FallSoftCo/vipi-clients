#!/usr/bin/env python3
"""Prepare a private, reviewable client-source archive from one committed revision.

No Git history, backend, operations, credentials, private receipts or research
conversation datasets are selected. This command neither publishes nor signs a
release. Native builds, dependency compatibility and the final distribution
review remain separate from this archive's exact-file verification.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import posixpath
import shutil
import subprocess
import tarfile

TREES = ("android", "ios", "data", "language-packs")
FILES = (
    "CLIENT_SOURCE.md", "vendor/cld2",
    "scripts/build-android.sh", "scripts/build-android-speech-data.py",
    "scripts/android-dependency-inventory.gradle", "scripts/collect-android-notices.py",
    "scripts/collect-cld2-notices.py",
    "scripts/sync-immersion-notice.py",
    "scripts/check-android-release.py", "scripts/check-bundled-lexical.py",
    "scripts/check-source-context-assets.py",
    "scripts/prepare-ios-project.sh", "scripts/prepare-client-source.py",
    "qa/immersion/local-release-r01/provenance.json",
    "qa/immersion/corpus.json", "qa/immersion/speech.json", "qa/immersion/speech-lengths.json",
    "qa/immersion/source_lookup_experiment/controls.json",
    "qa/immersion/source_lookup_experiment/native-pilot-protocol.json",
    "qa/immersion/additive-selection-r01/fixtures.json",
    "qa/immersion/additive-selection-r01/identity-fixtures.json",
    "qa/immersion/additive-selection-r01/starter-identity-fixtures.json",
    "qa/backup/ascii.vipihistory", "qa/backup/unicode.vipihistory",
    "qa/backup/android-history-v1.vipihistory", "qa/backup/ios-history-v1.vipihistory",
    "qa/backup/vectors.json", "qa/backup/format-v1.json", "qa/backup/history_v1.py",
)
FIXTURE_TREES = ("qa/packs/signed-pack-fixtures", "qa/immersion/installer-fixture-assets")
EXCLUDED = frozenset(("android/BUILDING.md", "ios/BUILDING.md",
    "android/app/src/androidTest/java/co/fallsoft/vipi/ProfileSnapshotCompareDeviceTest.kt"))
EXCLUDED_SUBTREES = ("language-packs/expansion-starter-20261117-r01/",
    "language-packs/expansion-starter-20261117-r02/")
EXCLUSION_REASONS = {
    "android/BUILDING.md": "Internal host-specific build instructions",
    "ios/BUILDING.md": "Internal host-specific build instructions",
    "android/app/src/androidTest/java/co/fallsoft/vipi/ProfileSnapshotCompareDeviceTest.kt": "Private account-state diagnostic, not a client build input",
    "language-packs/expansion-starter-20261117-r01/": "Inactive experimental language pack, not in the active catalog",
    "language-packs/expansion-starter-20261117-r02/": "Inactive experimental language pack, not in the active catalog",
}


def excluded_source(name):
    return name in EXCLUDED or any(name.startswith(prefix) for prefix in EXCLUDED_SUBTREES)


def sha_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("Unsafe archive name")
    return name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--lexical-assets", type=Path)
    parser.add_argument("--upstream-root", required=True, type=Path)
    parser.add_argument("--upstream-manifest", required=True, type=Path)
    parser.add_argument("--upstream-manifest-sha256", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    revision = subprocess.check_output(["git", "rev-parse", "--verify", args.revision + "^{commit}"], cwd=root, text=True).strip()
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Output exists; inspect the original result instead of overwriting it")
    if sha_file(args.upstream_manifest) != args.upstream_manifest_sha256:
        raise ValueError("Upstream source manifest differs from the reviewed manifest")
    upstream = json.loads(args.upstream_manifest.read_text())["files"]
    upstream = [r for r in upstream if r["path"].endswith((".tar.gz", ".crate"))]
    if not upstream:
        raise ValueError("No retained upstream sources")
    for row in upstream:
        safe_name(row["path"])
        path = args.upstream_root / row["path"]
        if path.is_symlink() or path.stat().st_size != row["bytes"] or sha_file(path) != row["sha256"]:
            raise ValueError("Upstream archive differs: " + row["path"])

    catalog_raw = subprocess.check_output(["git", "show", revision + ":data/lexical/catalog.json"], cwd=root)
    catalog = json.loads(catalog_raw)
    assets = args.lexical_assets or root / "data/lexical"
    extra = []
    for row in catalog["files"]:
        if row["file"] != row["id"] + ".sqlite.zlib":
            raise ValueError("Unexpected lexical artifact name")
        name = safe_name(row["file"])
        path = assets / name
        if path.is_symlink() or path.stat().st_size != row["compressed_bytes"] or sha_file(path) != row["compressed_sha256"]:
            raise ValueError("Generated lexical asset differs: " + name)
        extra.append(("data/lexical/" + name, path, row["compressed_bytes"], row["compressed_sha256"]))
    selections = [*TREES, *FILES, *FIXTURE_TREES]
    # Check every explicit input exists in this revision before creating output.
    for name in selections:
        subprocess.run(["git", "cat-file", "-e", revision + ":" + name], cwd=root, check=True, stdout=subprocess.DEVNULL)
    listing = subprocess.check_output(["git", "ls-tree", "-rlz", revision, "--", *selections], cwd=root)
    blobs = {}
    for item in listing.split(b"\0"):
        if not item:
            continue
        metadata, raw_name = item.split(b"\t", 1)
        mode, kind, oid, size = metadata.decode().split()
        name = safe_name(raw_name.decode())
        if excluded_source(name):
            continue
        if kind != "blob" or mode not in ("100644", "100755", "120000"):
            raise ValueError("Source export needs explicit handling for: " + name)
        blobs[name] = {"git_blob": oid, "bytes": int(size), "mode": mode}
    additional_bytes = sum(x["bytes"] for x in blobs.values()) + sum(x[2] for x in extra) + sum(x["bytes"] for x in upstream)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Streaming avoids an extracted duplicate tree. Allow uncompressed payload
    # plus manifest/stream overhead and preserve a separate 1 GiB margin.
    if shutil.disk_usage(output.parent).free < additional_bytes + 1024**3:
        raise ValueError("Insufficient disk headroom for the complete archive")
    output.mkdir(mode=0o700)
    manifest = {"schema": "vipi-private-client-source-candidate-1", "revision": revision,
        "published": False, "complete_corresponding_source_claim": False,
        "included": selections, "upstream_manifest_sha256": args.upstream_manifest_sha256,
        "exclusions": ["Git history", "backend and operations", "private receipts", "external conversation research datasets", "signing and provider credentials", "Internal host-specific build instructions"],
        "excluded_source_paths": sorted(EXCLUDED),
        "excluded_source_subtrees": list(EXCLUDED_SUBTREES),
        "excluded_source_reasons": EXCLUSION_REASONS,
        "files": {}, "remaining": ["Final signed build/source identity", "Native dependency source-build instructions and complete combined dependency review", "Secret/privacy and language-data attribution review of this exact archive", "Public publication and store submission"]}
    archive_path = output / "vipi-client-source-candidate.tar.gz"
    with archive_path.open("xb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=1) as compressed, tarfile.open(fileobj=compressed, mode="w|") as target:
        def add(name, stream, size, mode=0o644):
            safe_name(name)
            if name in manifest["files"]:
                raise ValueError("Duplicate source member: " + name)
            info = tarfile.TarInfo(name); info.size = size; info.mode = mode; info.mtime = 0
            # One source blob at a time (largest retained file is about24MiB).
            content = stream.read(size + 1)
            if len(content) != size:
                raise ValueError("Input length changed: " + name)
            target.addfile(info, io.BytesIO(content))
            manifest["files"][name] = {"bytes": size, "sha256": hashlib.sha256(content).hexdigest()}
            return content

        command = subprocess.Popen(["git", "archive", "--format=tar", revision, "--", *selections], cwd=root, stdout=subprocess.PIPE)
        try:
            with tarfile.open(fileobj=command.stdout, mode="r|") as source:
                for member in source:
                    if member.isdir():
                        continue
                    if excluded_source(member.name):
                        continue
                    if member.name not in blobs:
                        raise ValueError("Unexpected source member")
                    expected = blobs[member.name]
                    if member.issym() and expected["mode"] == "120000":
                        # Preserve the upstream eSpeak compatibility header link;
                        # never dereference host files or permit an escaping link.
                        name = member.name
                        link = member.linkname
                        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), link))
                        if link.startswith("/") or resolved not in blobs or blobs[resolved]["mode"] == "120000":
                            raise ValueError("Source symlink does not resolve to an included regular source file")
                        content = link.encode()
                        info = tarfile.TarInfo(name); info.type = tarfile.SYMTYPE
                        info.linkname = link; info.mode = 0o777
                        target.addfile(info)
                        manifest["files"][name] = {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(), "symlink": link, "resolved_member": resolved}
                    elif member.isfile() and expected["mode"] != "120000":
                        content = add(member.name, source.extractfile(member), member.size, int(expected["mode"], 8) & 0o777)
                    else:
                        raise ValueError("Source entry type differs from Git")
                    git_hash = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
                    if git_hash != expected["git_blob"]:
                        raise ValueError("Source blob identity differs: " + member.name)
                    manifest["files"][member.name]["git_blob"] = git_hash
            if command.wait() != 0 or set(blobs) - set(manifest["files"]):
                raise ValueError("Incomplete Git archive")
        finally:
            if command.poll() is None:
                command.terminate(); command.wait(timeout=10)
        for name, path, size, expected_sha in extra:
            with path.open("rb") as stream:
                content = add(name, stream, size)
            if hashlib.sha256(content).hexdigest() != expected_sha:
                raise ValueError("Lexical artifact changed during capture")
        for row in upstream:
            name = "upstream-sources/" + row["path"]
            with (args.upstream_root / row["path"]).open("rb") as stream:
                content = add(name, stream, row["bytes"])
            if hashlib.sha256(content).hexdigest() != row["sha256"]:
                raise ValueError("Upstream archive changed during capture")
        data = (json.dumps(manifest, indent=2) + "\n").encode()
        info = tarfile.TarInfo("SOURCE_MANIFEST.json"); info.size = len(data); info.mode = 0o644
        target.addfile(info, io.BytesIO(data))
    (output / "manifest.json").write_bytes(data)
    receipt = {"state": "private_candidate_prepared", "revision": revision,
        "archive": archive_path.name, "bytes": archive_path.stat().st_size,
        "sha256": sha_file(archive_path), "manifest_sha256": hashlib.sha256(data).hexdigest(),
        "files": len(manifest["files"]), "generated_lexical_artifacts": len(extra),
        "retained_upstream_archives": len(upstream), "published": False}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
