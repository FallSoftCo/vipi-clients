#!/usr/bin/env python3
"""Kill only Vipi's own emulator/simulator process while its debug transaction is armed.

Run on OZZZ-OS for Android, or the Mac build host for iOS, after a successful build.
The app uses a fresh synthetic account. This is process-crash, not power-loss proof.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument("platform", choices=["android", "ios"])
parser.add_argument("revision")
args = parser.parse_args()
assert args.revision.isdigit() and len(args.revision) == 3
root = Path(__file__).resolve().parents[1]
receipt = root / "artifacts" / f"storage-crash-{args.platform}-{args.revision}.json"
assert not receipt.exists(), "Use a fresh receipt revision"
bundle = "co.fallsoft.vipi"
result = {
    "platform": args.platform,
    "startedAt": time.time(),
    "scope": "synthetic native SQLite process termination; not power loss or live relay",
}


def command(*values):
    return subprocess.check_output(values, text=True, stderr=subprocess.PIPE).strip()


def wait_for(read, accept):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            value = read()
            if accept(value):
                return value
        except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
            pass
        time.sleep(0.1)
    raise RuntimeError("Timed out waiting for the exact native probe state")


stop = None
try:
    if args.platform == "android":
        assert socket.gethostname() == "ozzz-aosp"
        adb = "/aosp/ozzz-android-toolchain/sdk/platform-tools/adb"
        device = "emulator-5620"

        def call(*values):
            return command(adb, "-s", device, *values)

        stop = lambda: call("shell", "am", "force-stop", bundle)
        apk = root / "android/app/build/outputs/apk/debug/app-debug.apk"
        result["artifactSHA256"] = hashlib.sha256(apk.read_bytes()).hexdigest()
        assert "Success" in call("install", "-r", str(apk))
        stop()
        call(
            "shell",
            "run-as",
            bundle,
            "rm",
            "-f",
            "files/storage-crash-armed",
            "files/storage-crash-receipt.json",
        )
        call(
            "shell",
            "am",
            "start",
            "-n",
            bundle + "/.MainActivity",
            "--es",
            "vipi_storage_probe",
            "stage",
        )
        wait_for(
            lambda: call("shell", "run-as", bundle, "cat", "files/storage-crash-armed"),
            lambda text: text == "armed",
        )
        probe = json.loads(
            call("shell", "run-as", bundle, "cat", "files/storage-crash-probe.json")
        )
        result["terminatedPID"] = int(call("shell", "pidof", bundle))
        stop()
        pid = subprocess.run(
            [adb, "-s", device, "shell", "pidof", bundle],
            capture_output=True,
            text=True,
        )
        assert not pid.stdout.strip(), "Process survived force-stop"
        call(
            "shell",
            "am",
            "start",
            "-n",
            bundle + "/.MainActivity",
            "--es",
            "vipi_storage_probe",
            "verify",
        )
        native = wait_for(
            lambda: json.loads(
                call(
                    "shell", "run-as", bundle, "cat", "files/storage-crash-receipt.json"
                )
            ),
            lambda value: "status" in value,
        )
        assert native.get("account") == probe["account"], "Stale receipt"
        result.update(device=device, termination="am force-stop")
    else:
        device = "46CB569D-EA59-40E3-82CC-F4A0F36EDB87"

        def call(*values):
            return command("xcrun", "simctl", *values)

        stop = lambda: subprocess.run(
            ["xcrun", "simctl", "terminate", device, bundle], capture_output=True
        )
        app = root / "build/ios/Build/Products/Debug-iphonesimulator/Vipi.app"
        result["artifactSHA256"] = hashlib.sha256(
            (app / "Vipi").read_bytes()
        ).hexdigest()
        stop()
        call("install", device, str(app))
        container = (
            Path(call("get_app_container", device, bundle, "data")) / "Documents"
        )
        for name in ["storage-crash-armed", "storage-crash-receipt.json"]:
            (container / name).unlink(missing_ok=True)
        launched = call("launch", device, bundle, "-vipi-storage-stage")
        assert launched.startswith(bundle + ":")
        pid = int(launched.rsplit(":", 1)[1])
        result["terminatedPID"] = pid
        wait_for(
            lambda: (container / "storage-crash-armed").read_text(),
            lambda text: text == "armed",
        )
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.3)
        call("launch", device, bundle, "-vipi-storage-verify")
        native = wait_for(
            lambda: json.loads((container / "storage-crash-receipt.json").read_text()),
            lambda value: "status" in value,
        )
        result.update(device=device, termination="SIGKILL")
    result["native"] = native
    assert native["status"] == "passed", native
    result["status"] = "passed"
except Exception as error:
    result.update(status="failed", error=type(error).__name__ + ": " + str(error))
    if stop:
        stop()
    raise
finally:
    result["finishedAt"] = time.time()
    receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "receipt": str(receipt)}))
