#!/usr/bin/env python3
"""Replay an explicitly staged lexical candidate in the owned iOS simulator."""

import argparse, hashlib, json, os, subprocess
from pathlib import Path

ROOT = Path("/Users/Apple/Development/vipi")
DEVICE = "46CB569D-EA59-40E3-82CC-F4A0F36EDB87"


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def command(args):
    return subprocess.check_output(args, stdin=subprocess.DEVNULL).decode().strip()


def main():
    p = argparse.ArgumentParser()
    for name in ["run", "fixture", "witness"]:
        p.add_argument("--" + name, required=True)
    p.add_argument("--build", action="store_true")
    a = p.parse_args()
    assert all(len(v) == 3 and v.isdigit() for v in [a.run, a.fixture, a.witness])
    fixture = ROOT / ("artifacts/lexical-qualification-" + a.fixture)
    witness = ROOT / ("artifacts/context-witnesses-" + a.witness) / "witnesses.sqlite"
    pin = json.loads(witness.with_name("receipt.json").read_text())
    assert pin["complete"] and sha(witness) == pin["sha256"]
    manifest = json.loads((fixture / "manifest.json").read_text())
    assert sha(fixture / "cases.json") == manifest["cases_sha256"]
    for row in manifest["shards"]:
        f = fixture / (row["language"] + ".sqlite")
        assert f.stat().st_size == row["bytes"] and sha(f) == row["sha256"]
    app = Path(
        command(
            ["xcrun", "simctl", "get_app_container", DEVICE, "co.fallsoft.vipi", "data"]
        )
    )
    docs = app / "Documents"
    staged = docs / fixture.name
    if staged.exists():
        assert staged.is_symlink() and staged.resolve() == fixture.resolve()
    else:
        staged.symlink_to(fixture)
    destination = docs / ("context-witnesses-" + a.witness + ".sqlite")
    if destination.exists():
        assert sha(destination) == pin["sha256"]
    else:
        os.link(witness, destination)
    control = docs / "lexical-qa-run.txt"
    before = control.read_bytes() if control.exists() else None
    report = ROOT / ("artifacts/lexical-coverage-simulator-" + a.run + ".json")
    result = ROOT / ("artifacts/lexical-candidate-simulator-" + a.run + ".xcresult")
    native = docs / ("lexical-coverage-" + a.run + ".json")
    assert not report.exists() and not result.exists() and not native.exists()
    state = ROOT / ("artifacts/lexical-candidate-simulator-" + a.run + "-controls.json")
    assert not state.exists()
    state.write_text(
        json.dumps(
            dict(
                previous_control=before.decode() if before is not None else None,
                restored=False,
            ),
            indent=2,
        )
        + "\n"
    )
    control.write_text(" ".join([a.run, a.fixture, pin["sha256"], a.witness]) + "\n")
    catalog_sha = sha(ROOT / "data/lexical/catalog.json")
    try:
        with (ROOT / ("artifacts/lexical-candidate-simulator-" + a.run + ".log")).open(
            "x"
        ) as log:
            done = subprocess.run(
                [
                    "xcodebuild",
                    "-workspace",
                    "Vipi.xcworkspace",
                    "-scheme",
                    "VipiSimulator",
                    "-configuration",
                    "Simulator",
                    "-sdk",
                    "iphonesimulator",
                    "-destination",
                    "platform=iOS Simulator,id=" + DEVICE + ",arch=arm64",
                    "-derivedDataPath",
                    "../build/ios-simulator",
                    "-parallel-testing-enabled",
                    "NO",
                    "-collect-test-diagnostics",
                    "never",
                    "-only-testing:VipiCryptoTests/LexicalCoverageTests",
                    "-resultBundlePath",
                    str(result),
                    "ARCHS=arm64",
                    "EXCLUDED_ARCHS=",
                    "CODE_SIGNING_ALLOWED=YES",
                    "CODE_SIGN_IDENTITY=-",
                    "test" if a.build else "test-without-building",
                ],
                cwd=ROOT / "ios",
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        # Xcode installation can replace the simulator container UUID.
        current = (
            Path(
                command(
                    [
                        "xcrun",
                        "simctl",
                        "get_app_container",
                        DEVICE,
                        "co.fallsoft.vipi",
                        "data",
                    ]
                )
            )
            / "Documents"
        )
        native = current / ("lexical-coverage-" + a.run + ".json")
        if native.exists():
            report.write_bytes(native.read_bytes())
        assert done.returncode == 0, "Native test failed; inspect log and report."
        value = json.loads(report.read_text())
        assert (
            value["complete"]
            and value["passed"]
            and value["run"] == a.run
            and not value["failures"]
        )
        assert (
            value["manifest_sha256"] == sha(fixture / "manifest.json")
            and value["witness_sha256"] == pin["sha256"]
        )
        assert sha(ROOT / "data/lexical/catalog.json") == catalog_sha
        print(
            json.dumps(
                dict(
                    complete=True,
                    cases=len(value["outcomes"]),
                    report_sha256=sha(report),
                    production_promoted=False,
                )
            ),
            flush=True,
        )
    finally:
        current = (
            Path(
                command(
                    [
                        "xcrun",
                        "simctl",
                        "get_app_container",
                        DEVICE,
                        "co.fallsoft.vipi",
                        "data",
                    ]
                )
            )
            / "Documents"
        )
        control = current / "lexical-qa-run.txt"
        if before is None:
            control.unlink(missing_ok=True)
        else:
            control.write_bytes(before)
        state.write_text(
            json.dumps(
                dict(
                    previous_control=before.decode() if before is not None else None,
                    restored=True,
                ),
                indent=2,
            )
            + "\n"
        )


if __name__ == "__main__":
    main()
