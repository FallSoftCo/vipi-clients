#!/usr/bin/env python3
"""Copy the pinned local language detector notices into both native clients."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor/cld2"
PINS = json.loads((VENDOR / "source-manifest.json").read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    apple_root = ROOT / "ios/Vipi/ThirdPartyNotices"
    android_root = ROOT / "android/app/src/main/assets/legal/upstream"
    apple_path = apple_root / "index.json"
    android_path = android_root / "index.json"
    apple = json.loads(apple_path.read_text())
    android = json.loads(android_path.read_text())
    files = []
    for name in ("LICENSE", "NOTICE"):
        data = (VENDOR / name).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        assert PINS["cld2/" + name] == {"bytes": len(data), "sha256": sha}
        data.decode("utf-8", errors="strict")
        filename = "cld2-" + name.lower() + "-" + sha + ".txt"
        files.append((name, data, sha, filename))
    # Validate both upstream files before writing any generated assets.
    for name, data, sha, filename in files:
        for directory in (apple_root, android_root):
            (directory / filename).write_bytes(data)
        identifier = "cld2-" + name.lower()
        apple = [entry for entry in apple if entry["id"] != identifier]
        apple.append(
            {
                "id": identifier,
                "title": "CLD2 — "
                + (
                    "Apache 2.0 license"
                    if name == "LICENSE"
                    else "copyright and modifications"
                ),
                "file": filename,
                "sha256": sha,
                "origin": "vendor/cld2/" + name,
            }
        )
        coordinate = "CLD2 (pycld2 0.42 source) — " + name
        android["licenses"] = [
            entry for entry in android["licenses"] if entry["coordinate"] != coordinate
        ]
        android["licenses"].append(
            {
                "coordinate": coordinate,
                "url": "https://github.com/aboSamoor/pycld2",
                "asset": "legal/upstream/" + filename,
                "sha256": sha,
                "bytes": len(data),
            }
        )
    write_json(apple_path, apple)
    write_json(android_path, android)
    print(
        "Pinned CLD2 license and modification notice included in both native notice indexes."
    )


if __name__ == "__main__":
    main()
