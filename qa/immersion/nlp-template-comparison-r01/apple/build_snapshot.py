#!/usr/bin/env python3
"""Compile a frozen QA probe against clean exported controls in the existing VM.

Admission/consumer checks belong to the caller and must cover compilation plus
retained output. This script never downloads tools, packages, models or assets.
"""
from pathlib import Path
import argparse
import hashlib
import json
import platform
import plistlib
import subprocess
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--probe-sha256", required=True)
    parser.add_argument("--support-manifest", type=Path)
    parser.add_argument("--module-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "Darwin" or Path.home() != Path("/Users/lume"):
        raise RuntimeError("Use the existing authorized Apple development VM")
    if not args.module_cache.is_dir():
        raise FileNotFoundError("Existing qualified module cache required")
    manifest = json.loads((args.snapshot / "source-manifest.json").read_text())
    for name, expected in manifest["production_source"].items():
        if sha(args.snapshot / "production" / name) != expected:
            raise ValueError(name)
    for name, expected in manifest["generated_source"].items():
        if sha(args.snapshot / name) != expected:
            raise ValueError(name)
    if sha(args.probe) != args.probe_sha256:
        raise ValueError("Probe differs from frozen source")
    support = []
    if args.support_manifest:
        for name, expected in json.loads(args.support_manifest.read_text()).items():
            if Path(name).name != name or not name.endswith(".swift"):
                raise ValueError("Support manifest must name local Swift files")
            path = args.probe.parent / name
            if sha(path) != expected:
                raise ValueError("Support source differs from frozen manifest: " + name)
            support.append(path)
    args.output.mkdir(parents=True, exist_ok=False)
    app = args.output / "VipiNLPComparison.app"
    executable = app / "Contents/MacOS/vipi-nlp-compare"
    resources = app / "Contents/Resources"
    executable.parent.mkdir(parents=True)
    (resources / "immersion").mkdir(parents=True)
    for source, destination in [
        ("data/immersion/catalog.json", resources / "immersion/catalog.json"),
        ("data/examples/sentence-readings.json", resources / "sentence-readings.json")]:
        destination.write_bytes((args.snapshot / "production" / source).read_bytes())
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": "co.fallsoft.vipi.qa.nlp-comparison",
        "CFBundleExecutable": executable.name, "CFBundlePackageType": "APPL",
        "CFBundleName": "Vipi NLP comparison", "CFBundleVersion": "1"}))
    sdk = subprocess.check_output(["xcrun", "--sdk", "macosx", "--show-sdk-path"], text=True).strip()
    sources = sorted((args.snapshot / "production/ios/VipiCore/Sources/VipiCore").glob("*.swift"))
    sources += [args.snapshot / "NativeBoundaries.swift", args.snapshot / "NativeReferences.swift", *support, args.probe]
    command = ["xcrun", "swiftc", "-parse-as-library", "-O", "-j", "2",
               "-target", "arm64-apple-macosx26.4", "-sdk", sdk,
               "-module-cache-path", str(args.module_cache),
               "-module-name", "VipiNLPComparison", *map(str, sources), "-o", str(executable)]
    started = time.monotonic()
    with (args.output / "compiler.log").open("w") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    receipt = {"schema": "vipi.apple-nlp-build.1", "exit": result.returncode,
               "seconds": time.monotonic() - started,
               "production_commit": manifest["commit"],
               "source_manifest_sha256": sha(args.snapshot / "source-manifest.json"),
               "probe_sha256": args.probe_sha256, "builder_sha256": sha(Path(__file__)),
               "support_source": {p.name: sha(p) for p in support},
               "sdk": sdk, "system": platform.platform(), "command": command,
               "executable_sha256": sha(executable) if executable.exists() else None,
               "bundle_resources": {str(p.relative_to(resources)): sha(p)
                                    for p in resources.rglob("*") if p.is_file()},
               "models_or_dependencies_downloaded": False, "app_runtime_activated": False,
               "resource_admission": "Caller must retain separate native/guest admission and peak samples"}
    (args.output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: v for k, v in receipt.items() if k not in {"command", "bundle_resources"}}))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
