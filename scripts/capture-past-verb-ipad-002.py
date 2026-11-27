#!/usr/bin/env python3
"""Physical Apple Translation and playback capture in the Mac login session."""

from pathlib import Path
import subprocess, json, hashlib, time, os

ROOT = Path("/Users/Apple/Development/vipi")
DEVICE = "7B6D180F-1D57-5036-8E42-C057698FBAB2"


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main():
    os.chdir(ROOT)
    stage = ROOT / "artifacts/ipad-past-capture-002"
    stage.mkdir(exist_ok=False)
    protocol = ROOT / "artifacts/ipad-past-capture-001/protocol.json"
    assert (
        sha(protocol)
        == "35e82b0c46a4b6e88677a52f8a0b6cfe0309c8001484effdd9b72a81e36cc300"
    )

    def transfer(direction, source, destination, name):
        result = subprocess.run(
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
        (stage / (name + ".log")).write_text(result.stdout + result.stderr)
        return result.returncode

    for source, destination in [
        ("Documents/phrase-protocol.json", "previous-protocol.json"),
        ("Documents/speech-qa/player-001.json", "previous-player.json"),
    ]:
        assert transfer("from", source, stage / destination, destination + ".copy") == 0
    assert (
        transfer("to", protocol, "Documents/phrase-protocol.json", "stage-protocol")
        == 0
    )
    start = time.time()
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
        "-allowProvisioningUpdates",
        "-parallel-testing-enabled",
        "NO",
        "-collect-test-diagnostics",
        "never",
        "-test-timeouts-enabled",
        "YES",
        "-maximum-test-execution-time-allowance",
        "600",
        "-only-testing:VipiCryptoTests/LocalSpeechTests/testActualPlayerCompletionAndCancellation",
        "-only-testing:VipiCryptoTests/TranslationPhraseTests",
        "-resultBundlePath",
        str(stage / "capture.xcresult"),
        "test",
    ]
    try:
        with (stage / "capture.log").open("x") as log:
            run = subprocess.run(
                command,
                cwd=ROOT / "ios",
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
    finally:
        restored = (
            transfer(
                "to",
                stage / "previous-protocol.json",
                "Documents/phrase-protocol.json",
                "restore-protocol",
            )
            == 0
        )
    outputs = {}
    for source, name in [
        ("Documents/phrase-observations-apple-450.json", "apple-translations.json"),
        ("Documents/speech-qa/player-001.json", "physical-player.json"),
    ]:
        code = transfer("from", source, stage / name, name + ".copy")
        outputs[name] = dict(copy_exit=code)
        if code == 0:
            outputs[name].update(
                sha256=sha(stage / name), bytes=(stage / name).stat().st_size
            )
    complete = (
        run.returncode == 0
        and restored
        and all(v["copy_exit"] == 0 for v in outputs.values())
    )
    if complete:
        captured = json.loads((stage / "apple-translations.json").read_text())
        assert (
            captured["complete"]
            and captured["cases_completed"] == 48
            and captured["protocol_sha256"] == sha(protocol)
        )
    receipt = dict(
        complete=complete,
        xcode_exit=run.returncode,
        device=DEVICE,
        physical=True,
        started=start,
        elapsed_seconds=time.time() - start,
        protocol_sha256=sha(protocol),
        original_protocol_restored=restored,
        outputs=outputs,
        acoustic_listening_accepted=False,
        store_ready=False,
        app_bundled_catalog_sha256=sha(
            ROOT
            / "build/ios-device/Build/Products/Debug-iphoneos/Vipi.app/lexical/catalog.json"
        ),
    )
    (stage / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt), flush=True)
    assert complete


if __name__ == "__main__":
    main()
