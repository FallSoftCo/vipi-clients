#!/usr/bin/env python3
"""Drive the existing Google voice-download UI on Vipi's dedicated emulator only."""

import json
from pathlib import Path
import re
import socket
import subprocess
import time
import sys
import xml.etree.ElementTree as ET

assert socket.gethostname() == "ozzz-aosp"
adb = ["/aosp/ozzz-android-toolchain/sdk/platform-tools/adb", "-s", "emulator-5620"]


def shell(*args):
    return subprocess.check_output(adb + ["shell", *args], text=True, timeout=45)


assert "sdk_gphone" in shell("getprop", "ro.product.model")


def nodes():
    shell("uiautomator", "dump", "/sdcard/vipi-voice-ui.xml")
    return list(ET.fromstring(shell("cat", "/sdcard/vipi-voice-ui.xml")).iter("node"))


def label(node):
    return node.get("text") or node.get("content-desc") or ""


def has_voices(page):
    return any(re.fullmatch(r"Voice [IVX]+", label(n)) for n in page)


def tap(node):
    x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds")))
    shell("input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2))


targets = [
    "Arabic",
    "Chinese (China)",
    "English (United States)",
    "French (France)",
    "German (Germany)",
    "Italian (Italy)",
    "Japanese (Japan)",
    "Korean (South Korea)",
    "Portuguese (Brazil)",
    "Spanish (Spain)",
]
receipt = []
revision = sys.argv[1] if len(sys.argv) == 2 else "001"
assert revision.isdigit() and len(revision) == 3
path = Path(f"/aosp/development/vipi/artifacts/android-voice-downloads-{revision}.json")
# Caller has the voice language list open. If a single-language page is open,
# return one level, rather than launching another unrelated activity.
current = nodes()
if any(label(n) == "Delete voice pack" for n in current) or has_voices(current):
    shell("input", "keyevent", "4")
for _ in range(10):
    shell("input", "swipe", "540", "600", "540", "2200", "150")
for target in targets:
    found = None
    for _ in range(18):
        current = nodes()
        found = next((n for n in current if label(n) == target), None)
        if found is not None:
            break
        # A slow, overlapping scroll avoids flinging past a language row.
        shell("input", "swipe", "540", "2000", "540", "1100", "700")
    if found is None:
        receipt.append(
            {
                "language": target,
                "status": "not_found",
                "visible": [label(n) for n in current if label(n)],
            }
        )
        path.write_text(json.dumps(receipt, indent=2))
        print(json.dumps(receipt[-1]), flush=True)
        raise SystemExit(1)
    tap(found)
    page = nodes()
    download = next((n for n in page if label(n) == "Download voice pack"), None)
    if download is not None:
        tap(download)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        page = nodes()
        if any(label(n) == "Delete voice pack" for n in page) or has_voices(page):
            break
        time.sleep(1)
    else:
        raise RuntimeError("Voice download did not complete: " + target)
    receipt.append(
        {
            "language": target,
            "status": "available_in_native_voice_ui",
            "download_requested": download is not None,
        }
    )
    path.write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt[-1]), flush=True)
    shell("input", "keyevent", "4")
