#!/usr/bin/env python3
"""Replay captured translations on the attached iPad using its current signed build."""

import argparse, hashlib, json, platform, subprocess, time
from pathlib import Path

ROOT = Path("/Users/Apple/Development/vipi")
DEVICE = "7B6D180F-1D57-5036-8E42-C057698FBAB2"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--expected-catalog", required=True)
    a = p.parse_args()
    assert platform.system() == "Darwin" and len(a.run) == 3 and a.run.isdigit()
    cases = a.cases.resolve()
    inputs = json.loads(cases.read_text())
    assert isinstance(inputs, list) and inputs
    built = (
        ROOT
        / "build/ios-device/Build/Products/Debug-iphoneos/Vipi.app/lexical/catalog.json"
    )
    assert sha(built) == a.expected_catalog
    stage = ROOT / ("artifacts/ipad-bundled-replay-" + a.run)
    stage.mkdir(exist_ok=False)
    report = ROOT / ("artifacts/bundled-conversations-ipad-" + a.run + ".json")
    assert not report.exists()

    def transfer(direction, source, destination, label):
        r = subprocess.run(
            [
                "xcrun",
                "devicectl",
                "device",
                "copy",
                direction,
                "--device",
                DEVICE,
                "--domain-type",
                "appDataContainer",
                "--domain-identifier",
                "co.fallsoft.vipi",
                "--quiet",
                "--source",
                str(source),
                "--destination",
                str(destination),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )
        (stage / (label + ".log")).write_text(r.stdout + r.stderr)
        return r.returncode

    backups = {}
    for name in ["bundled-conversation-cases.json", "bundled-conversation-run.txt"]:
        dest = stage / ("previous-" + name)
        code = transfer("from", "Documents/" + name, dest, "backup-" + name)
        # These QA controls already exist on the owned iPad. A failed backup is
        # a real precondition failure, not permission to replace unknown state.
        assert code == 0, "Unable to preserve existing device QA control " + name
        backups[name] = dest
    control = stage / "run.txt"
    control.write_text(a.run + " " + sha(cases) + "\n")
    started = time.time()
    restored = {}
    try:
        assert (
            transfer(
                "to", cases, "Documents/bundled-conversation-cases.json", "stage-cases"
            )
            == 0
        )
        assert (
            transfer(
                "to", control, "Documents/bundled-conversation-run.txt", "stage-run"
            )
            == 0
        )
        command = [
            "xcodebuild",
            "-workspace",
            "Vipi.xcworkspace",
            "-scheme",
            "Vipi",
            "-configuration",
            "Debug",
            "-destination",
            "platform=iOS,id=" + DEVICE,
            "-derivedDataPath",
            "../build/ios-device",
            "-parallel-testing-enabled",
            "NO",
            "-collect-test-diagnostics",
            "never",
            "-only-testing:VipiCryptoTests/BundledConversationReplayTests",
            "-resultBundlePath",
            str(stage / "replay.xcresult"),
            "test-without-building",
        ]
        with (stage / "replay.log").open("x") as stream:
            r = subprocess.run(
                command,
                cwd=ROOT / "ios",
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
            )
    finally:
        for name, path in backups.items():
            restored[name] = (
                transfer("to", path, "Documents/" + name, "restore-" + name) == 0
            )
    copied = (
        transfer(
            "from",
            "Documents/bundled-conversations-" + a.run + ".json",
            report,
            "copy-report",
        )
        == 0
    )
    receipt = dict(
        xcode_exit=r.returncode,
        device=DEVICE,
        physical=True,
        restored=restored,
        elapsed_seconds=time.time() - started,
        cases_sha256=sha(cases),
        expected_catalog_sha256=a.expected_catalog,
        translation_reused=True,
        population_coverage_claim=False,
        complete=False,
    )
    if copied:
        value = json.loads(report.read_text())
        assert value["run"] == a.run
        receipt["report_sha256"] = sha(report)
        receipt["complete"] = (
            r.returncode == 0
            and all(restored.values())
            and value["complete"]
            and not value["failures"]
            and len(value["outcomes"]) == len(inputs)
            and value["cases_sha256"] == sha(cases)
            and value["bundled_catalog_sha256"] == a.expected_catalog
            and value["platform"] == "physical iOS device"
        )
        receipt["messages_with_spans"] = sum(
            bool(row["combined_spans"]) for row in value["outcomes"]
        )
        receipt["spans"] = sum(len(row["combined_spans"]) for row in value["outcomes"])
    (stage / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt), flush=True)
    assert receipt["complete"]


if __name__ == "__main__":
    main()
