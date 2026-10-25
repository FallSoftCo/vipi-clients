#!/usr/bin/env python3
"""Drive only Vipi's isolated release qualification package through public UI.

No test APK, app-process instrumentation, debug shortcuts or optimizer keep rules.
The package's synthetic onboarding state is cleared; real Vipi data is untouched.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

PACKAGE = "co.fallsoft.vipi.qualification"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--adb", required=True)
parser.add_argument("--serial", required=True)
parser.add_argument("--apk", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
assert args.serial.startswith("emulator-"), "Qualification is limited to an emulator"
assert not args.output.exists(), "Retain previous evidence"
args.output.mkdir(parents=True)
remote = "/data/local/tmp/vipi-release-qualification.xml"


def adb(*values, raw=False):
    result = subprocess.check_output([args.adb, "-s", args.serial, *values], timeout=45)
    return result if raw else result.decode()


def hierarchy():
    adb("shell", "uiautomator", "dump", "--compressed", remote)
    return ET.fromstring(adb("exec-out", "cat", remote))


def matching(root, attribute, value):
    return [n for n in root.iter("node") if n.get(attribute) == value]


def find(attribute, value, attempts=4):
    for _ in range(attempts):
        found = matching(hierarchy(), attribute, value)
        if found:
            return found[-1]
        time.sleep(.3)
    raise AssertionError(f"Missing UI element: {attribute}={value}")


def tap(node):
    x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds")))
    assert x2 > x1 and y2 > y1
    adb("shell", "input", "tap", str((x1+x2)//2), str((y1+y2)//2))


def capture(name):
    root = hierarchy()
    (args.output / f"{name}.xml").write_bytes(ET.tostring(root))
    (args.output / f"{name}.png").write_bytes(adb("exec-out", "screencap", "-p", raw=True))
    return root


receipt = {"package": PACKAGE, "emulator": args.serial, "apk_sha256": hashlib.sha256(args.apk.read_bytes()).hexdigest(),
           "method": "external adb UI automation; no app instrumentation", "status": "started",
           "limits": ["Authored previews only; no general translation accuracy claim", "x86 emulator; not ARM or a physical device", "Production sign-in remains intentionally unconfigured"]}
try:
    adb("install", "-r", str(args.apk))
    assert "Success" in adb("shell", "pm", "clear", PACKAGE)
    package_dump = adb("shell", "dumpsys", "package", PACKAGE)
    (args.output / "package.txt").write_text(package_dump)
    flag_lines = [line for line in package_dump.splitlines() if re.search(r"(?:pkgFlags|flags)=\[", line)]
    assert flag_lines and all("DEBUGGABLE" not in line and "ALLOW_BACKUP" not in line for line in flag_lines)
    launch = adb("shell", "am", "start", "-W", "-n", PACKAGE + "/co.fallsoft.vipi.MainActivity", "--es", "vipi_screen", "home", "--es", "vipi_source", "ja")
    (args.output / "launch.txt").write_text(launch)
    assert "Status: ok" in launch
    tap(find("text", "Find your language"))
    find("text", "English")  # release ignores the debug language/navigation extras
    tap(find("content-desc", "Choose the language you know"))
    for _ in range(5):
        root = hierarchy()
        matches = matching(root, "text", "Japanese")
        if matches:
            tap(matches[-1]); break
        # Scroll only the currently open dropdown's scrollable container.
        containers = [n for n in root.iter("node") if n.get("scrollable") == "true"]
        assert containers, "No language-menu scrolling surface"
        x1,y1,x2,y2 = map(int, re.findall(r"\d+", containers[-1].get("bounds")))
        adb("shell", "input", "swipe", str((x1+x2)//2), str(y2-30), str((x1+x2)//2), str(y1+30), "300")
    else:
        raise AssertionError("Japanese is not available")
    find("text", "Japanese")
    root = capture("japanese-spanish-preview")
    preview = ET.tostring(root, encoding="unicode")
    assert any(word in preview for word in ["mañana", "café", "río"]), "Missing authored Spanish replacements"
    tap(find("text", "Continue with Spanish"))
    button = find("text", "Continue to sign in")
    # The disabled control is represented by a parent; tapping cannot navigate.
    tap(button)
    assert matching(hierarchy(), "text", "Continue to sign in")
    boxes = [n for n in hierarchy().iter("node") if n.get("checkable") == "true"]
    assert len(boxes) == 1 and boxes[0].get("checked") == "false"
    tap(boxes[0]); tap(find("text", "Continue to sign in"))
    find("text", "Sign-in isn’t available yet. Please try again shortly.")
    capture("production-auth-unconfigured")
    adb("shell", "am", "force-stop", PACKAGE)
    adb("shell", "am", "start", "-W", "-n", PACKAGE + "/co.fallsoft.vipi.MainActivity")
    # Onboarding restarts honestly; language selection must persist independently.
    root = hierarchy()
    if matching(root, "text", "Find your language"):
        tap(find("text", "Find your language"))
    elif matching(root, "text", "Continue to sign in"):
        adb("shell", "input", "keyevent", "4")
    find("text", "Japanese")
    capture("restored-language-choice")
    receipt.update(status="passed", release_flags_checked=True, debug_extras_ignored=True,
                   japanese_tokenizer_preview=True, consent_gate=True, unconfigured_auth_fails_closed=True,
                   language_choice_persists=True)
finally:
    adb("shell", "rm", "-f", remote)
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt, indent=2))
