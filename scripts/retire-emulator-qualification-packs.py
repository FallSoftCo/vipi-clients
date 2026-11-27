#!/usr/bin/env python3
"""Retire exact superseded QA database copies on Vipi's dedicated emulator."""

import json
from pathlib import Path
import subprocess

ADB = ["/aosp/ozzz-android-toolchain/sdk/platform-tools/adb", "-s", "emulator-5620"]
PACKAGE = "co.fallsoft.vipi"


def output(*args):
    return subprocess.check_output(ADB + list(args), text=True)


def verify(revision):
    directory = "files/bilingual-qa/packs-" + revision
    receipt = json.loads(
        Path("artifacts/packs/bilingual-" + revision + "/receipt.json").read_text()
    )
    assert receipt["qualification_only_key"] and len(receipt["pairs"]) == 90
    actual = output(
        "exec-out",
        "run-as",
        PACKAGE,
        "find",
        directory,
        "-name",
        "vocabulary.sqlite",
        "-exec",
        "sha256sum",
        "{}",
        "+",
    )
    hashes = {line.split()[1]: line.split()[0] for line in actual.splitlines()}
    expected = {
        directory + "/" + p["pack_id"] + "/vocabulary.sqlite": p
        for p in receipt["pairs"]
    }
    assert hashes.keys() == expected.keys()
    assert all(
        hashes[path] == manifest["sha256"] for path, manifest in expected.items()
    )
    return [
        {"path": path, "sha256": manifest["sha256"], "bytes": manifest["bytes"]}
        for path, manifest in expected.items()
    ]


def main():
    record = Path("artifacts/emulator-pack-retirement-002.json")
    assert not record.exists()
    assert "sdk_gphone" in output("shell", "getprop", "ro.product.model")
    capture = json.loads(
        Path("artifacts/bilingual-android-pipeline-006.json").read_text()
    )
    assert capture["completed_pairs"] == 90 and all(
        p["status"] == "executed" for p in capture["results"]
    )
    # The dedicated QA app is the only possible reader of its private files.
    subprocess.run(ADB + ["shell", "am", "force-stop", PACKAGE], check=True)
    verify("006")
    files = verify("004") + verify("005")
    receipt = {
        "completed": False,
        "device": "emulator-5620",
        "replacement": "006",
        "files": files,
        "bytes": sum(p["bytes"] for p in files),
        "reader_exclusion": "dedicated test app force-stopped",
        "preserved": [
            "all current revision-006 databases",
            "all signed metadata",
            "test captures",
            "account and conversation data",
        ],
    }
    record.write_text(json.dumps(receipt, indent=2) + "\n")
    subprocess.run(
        ADB + ["exec-out", "run-as", PACKAGE, "rm", "--"] + [p["path"] for p in files],
        check=True,
    )
    receipt["completed"] = True
    record.write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                "completed": True,
                "databases": len(files),
                "logical_bytes": receipt["bytes"],
            }
        )
    )


if __name__ == "__main__":
    main()
