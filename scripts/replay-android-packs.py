#!/usr/bin/env python3
"""Signed-pack qualification on the dedicated emulator; no customer data."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

ADB = ["/aosp/ozzz-android-toolchain/sdk/platform-tools/adb", "-s", "emulator-5620"]
PACKAGE = "co.fallsoft.vipi"


def run(*args, **kwargs):
    return subprocess.run(ADB + list(args), check=True, **kwargs)


def main(args):
    assert args.revision.isdigit() and len(args.revision) == 3
    revision = args.revision
    packs = Path("artifacts/packs/bilingual-" + revision)
    receipt = json.loads((packs / "receipt.json").read_text())
    assert len(receipt["pairs"]) == 90 and receipt["qualification_only_key"]
    model = subprocess.check_output(
        ADB + ["shell", "getprop", "ro.product.model"], text=True
    )
    assert "sdk_gphone" in model
    folder = "files/bilingual-qa/packs-" + revision
    report = "bilingual-android-pipeline-" + revision + ".json"
    for path in (folder, "files/" + report):
        absent = subprocess.run(
            ADB + ["shell", "run-as", PACKAGE, "test", "-e", path], capture_output=True
        )
        assert absent.returncode == 1, "Preserve existing emulator qualification data"
    staging = Path("artifacts/android-packs-stage-" + revision + ".json")
    output = Path("artifacts") / report
    assert not staging.exists() and not output.exists()
    capture = "bilingual-android-pipeline-003.json"
    target_capture = subprocess.check_output(
        ADB + ["exec-out", "run-as", PACKAGE, "cat", "files/bilingual-qa/" + capture]
    )
    assert (
        hashlib.sha256(target_capture).digest()
        == hashlib.sha256((Path("artifacts") / capture).read_bytes()).digest()
    )
    started = time.monotonic()
    run("shell", "run-as", PACKAGE, "mkdir", "-p", folder)
    archive = subprocess.Popen(
        ["tar", "-C", str(packs), "-cf", "-", "."], stdout=subprocess.PIPE
    )
    try:
        run(
            "exec-in",
            "run-as",
            PACKAGE,
            "tar",
            "-xf",
            "-",
            "-C",
            folder,
            stdin=archive.stdout,
        )
    finally:
        archive.stdout.close()
    assert archive.wait() == 0
    staging.write_text(
        json.dumps(
            {
                "public_fixture_data_only": True,
                "copy_completed": True,
                "pairs": 90,
                "database_bytes": sum(p["bytes"] for p in receipt["pairs"]),
                "seconds": time.monotonic() - started,
                "native_hash_and_signature_checks": "pending instrumentation",
            },
            indent=2,
        )
        + "\n"
    )
    log = Path("artifacts/bilingual-android-pipeline-" + revision + ".log")
    assert not log.exists()
    with log.open("w") as file:
        run(
            "shell",
            "am",
            "instrument",
            "-w",
            "-r",
            "-e",
            "class",
            "co.fallsoft.vipi.BilingualPipelineDeviceTest",
            "-e",
            "vipiDedicatedEmulator",
            "true",
            "-e",
            "vipiRunID",
            revision,
            "-e",
            "vipiTranslationReport",
            capture,
            "-e",
            "vipiReportName",
            report,
            PACKAGE + ".test/androidx.test.runner.AndroidJUnitRunner",
            stdout=file,
            stderr=subprocess.STDOUT,
        )
    assert "OK (1 test)" in log.read_text(), "Inspect retained instrumentation failure"
    data = subprocess.check_output(
        ADB + ["exec-out", "run-as", PACKAGE, "cat", "files/" + report]
    )
    observed = json.loads(data)
    assert observed["completed_pairs"] == 90 and observed["network_absence_verified"]
    assert all(
        p["status"] == "executed"
        and len(p["samples"]) == 6
        and all(s["status"] == "executed" for s in p["samples"])
        for p in observed["results"]
    )
    output.write_bytes(data)
    print(
        json.dumps(
            {
                "native_execution": "passed",
                "pairs": 90,
                "samples": 540,
                "linguistic_acceptance": False,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    main(parser.parse_args())
