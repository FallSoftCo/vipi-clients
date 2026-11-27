#!/usr/bin/env python3
"""Update the owned QA emulator while temporarily freeing reproducible staging."""

import argparse, hashlib, json, subprocess
from pathlib import Path

ROOT = Path("/aosp/development/vipi")
ADB = ["/aosp/ozzz-android-toolchain/sdk/platform-tools/adb", "-s", "emulator-5620"]


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def adb(args):
    done = subprocess.run(
        ADB + args, stdin=subprocess.DEVNULL, capture_output=True, text=True
    )
    if done.returncode:
        raise RuntimeError(done.stdout + done.stderr)
    return done.stdout


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True)
    a = p.parse_args()
    assert len(a.run) == 3 and a.run.isdigit()
    assert adb(["emu", "avd", "name"]).splitlines()[0] == "vipi-api35-20261024"
    receipt = ROOT / ("artifacts/present-emulator-update-" + a.run + ".json")
    assert not receipt.exists()
    rows = []
    for language in ["en", "es"]:
        local = ROOT / ("artifacts/lexical-qualification-501/" + language + ".sqlite")
        device = "files/lexical-qualification-501/" + language + ".sqlite"
        digest = sha(local)
        assert (
            adb(["shell", "run-as", "co.fallsoft.vipi", "sha256sum", device]).split()[0]
            == digest
        )
        rows.append(dict(device=device, local=str(local), sha256=digest))
    state = dict(staging=rows, complete=False, restored=False, packages=[])

    def save():
        receipt.write_text(json.dumps(state, indent=2) + "\n")

    save()
    adb(["shell", "am", "force-stop", "co.fallsoft.vipi"])
    try:
        for row in rows:
            adb(["shell", "run-as", "co.fallsoft.vipi", "rm", row["device"]])
        for name in [
            "debug/app-debug.apk",
            "androidTest/debug/app-debug-androidTest.apk",
        ]:
            apk = ROOT / "android/app/build/outputs/apk" / name
            print(adb(["install", "-r", "--streaming", str(apk)]), flush=True)
            state["packages"].append(dict(path=str(apk), sha256=sha(apk)))
            save()
        state["complete"] = True
    except Exception as error:
        state["error"] = str(error)
        save()
        raise
    finally:
        for row in rows:
            with open(row["local"], "rb") as f:
                subprocess.run(
                    ADB
                    + [
                        "shell",
                        "run-as co.fallsoft.vipi sh -c 'cat > " + row["device"] + "'",
                    ],
                    stdin=f,
                    check=True,
                    capture_output=True,
                )
            assert (
                adb(
                    ["shell", "run-as", "co.fallsoft.vipi", "sha256sum", row["device"]]
                ).split()[0]
                == row["sha256"]
            )
        state["restored"] = True
        save()
    print(json.dumps(dict(complete=True, restored=True)), flush=True)


if __name__ == "__main__":
    main()
