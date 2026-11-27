#!/usr/bin/env python3
"""Capture a frozen public/authored phrase protocol on the owned offline emulator."""

import argparse, hashlib, json, subprocess
from pathlib import Path

ADB = "/aosp/ozzz-android-toolchain/sdk/platform-tools/adb"
DEVICE = "emulator-5620"


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert len(args.run) == 3 and args.run.isdigit()
    protocol = args.protocol.resolve()
    spec = json.loads(protocol.read_text())
    samples = spec["samples"]
    assert spec["schema"] == "vipi-local-phrase-probe-1" and samples
    args.output.mkdir(exist_ok=False, parents=True)
    stage = args.output.resolve()

    def adb(*parts, check=True):
        return subprocess.run(
            [ADB, "-s", DEVICE, *parts],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=check,
        )

    assert (
        adb("emu", "avd", "name").stdout.decode().splitlines()[0]
        == "vipi-api35-20261024"
    )
    old = adb(
        "exec-out",
        "run-as",
        "co.fallsoft.vipi",
        "cat",
        "files/immersion-qa/phrase-protocol.json",
    ).stdout
    backup = stage / "previous-protocol.json"
    backup.write_bytes(old)
    assert (
        adb(
            "shell",
            "run-as",
            "co.fallsoft.vipi",
            "test",
            "-e",
            "files/phrase-observations-" + args.run + ".json",
            check=False,
        ).returncode
        != 0
    )
    temp = "/data/local/tmp/vipi-phrase-protocol-" + args.run + ".json"

    def install(path):
        adb("push", str(path), temp)
        try:
            adb(
                "shell",
                "run-as",
                "co.fallsoft.vipi",
                "cp",
                temp,
                "files/immersion-qa/phrase-protocol.json",
            )
        finally:
            adb("shell", "rm", temp)

    restored = False
    try:
        install(protocol)
        command = [
            ADB,
            "-s",
            DEVICE,
            "shell",
            "am",
            "instrument",
            "-w",
            "-r",
            "-e",
            "class",
            "co.fallsoft.vipi.TranslationPhraseDeviceTest",
            "-e",
            "vipiDedicatedEmulator",
            "true",
            "-e",
            "vipiRunID",
            args.run,
            "co.fallsoft.vipi.test/androidx.test.runner.AndroidJUnitRunner",
        ]
        with (stage / "capture.log").open("x") as log:
            run = subprocess.run(
                command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT
            )
    finally:
        install(backup)
        restored = (
            adb(
                "exec-out",
                "run-as",
                "co.fallsoft.vipi",
                "cat",
                "files/immersion-qa/phrase-protocol.json",
            ).stdout
            == old
        )
    raw = adb(
        "exec-out",
        "run-as",
        "co.fallsoft.vipi",
        "cat",
        "files/phrase-observations-" + args.run + ".json",
    ).stdout
    capture = stage / "capture.json"
    capture.write_bytes(raw)
    data = json.loads(raw)
    assert (
        run.returncode == 0
        and restored
        and data["complete"]
        and data["network_absence_verified"]
    )
    assert data["protocol_sha256"] == sha(protocol) and data["cases_completed"] == len(
        samples
    ) == len(data["results"])
    expected = {(s["id"], s["source"], s["target"]): s for s in samples}
    seen = set()
    cases = []
    for row in data["results"]:
        key = (row["id"], row["source"], row["target"])
        assert key in expected and key not in seen and row["status"] == "executed"
        seen.add(key)
        assert (
            row["original"] == expected[key]["original"] and row["translation"].strip()
        )
        cases.append(
            {
                k: row[k]
                for k in [
                    "id",
                    "dataset",
                    "source",
                    "target",
                    "original",
                    "translation",
                ]
            }
        )
    assert seen == set(expected)
    (stage / "cases.json").write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n"
    )
    receipt = dict(
        complete=True,
        protocol_sha256=sha(protocol),
        capture_sha256=sha(capture),
        cases_sha256=sha(stage / "cases.json"),
        cases=len(cases),
        original_protocol_restored=restored,
        network_absence_verified=True,
        author_reference_translations_used=False,
        linguistic_acceptance=False,
    )
    (stage / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    main()
