"""Regenerate the frozen 38-row native Korean parity fixture from retained evidence.

Usage: python3 qa/immersion/prepare_android_reading_replay.py /disk/path/fixture.json
Push it to the owned QA app's files/android-korean-native-replay-r01.json, along
with android-default-reading-chat-plan-r01.json. NativeFullReadingDeviceTest
checks the exact fixture hash. No translation, inference or data download occurs.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
args = parser.parse_args()
assert not args.output.exists(), "Use a new output path; do not replace retained captures."
root = Path(__file__).resolve().parent / "korean-reading-cldr-r01"
rows = []
for name, expected in [
    ("guard-capture-r03", "e0816575c0bb02d7d263414b66b3bf8a5da75b6eb5d2e045541357df998fa7c4"),
    ("stress-capture-r03", "289b065c316121476b9f913229dd4f8a7390eb7a598bd534d060892683f6face"),
]:
    raw = gzip.decompress((root / "evidence" / (name + ".json.gz")).read_bytes())
    assert hashlib.sha256(raw).hexdigest() == expected
    rows.extend({key: value for key, value in row.items()
                 if key not in ("first_ns", "warm_ns", "guard_matches")}
                for row in json.loads(raw)["cases"])
assert len(rows) == 38
value = {"schema": "android-korean-native-replay-1", "case_count": 38,
         "source": "Exact pinned host outputs; replay is Android parity, not new semantic review",
         "cases": rows}
encoded = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
assert hashlib.sha256(encoded).hexdigest() == "7dace4e9781c3b504387aa5723d692b73a8ec300cc04c5459cc753d0e3a91de4"
args.output.write_bytes(encoded)
print(json.dumps({"rows": len(rows), "bytes": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest()}))
