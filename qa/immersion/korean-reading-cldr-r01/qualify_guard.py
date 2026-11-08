"""Capture exact UTF16 partitions, literal preservation, warm behavior and bounds."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("build_receipt", type=Path)
parser.add_argument("inputs", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
assert not args.output.exists()
build = json.loads(args.build_receipt.read_text())
rows = json.loads(args.inputs.read_text())["cases"]
framed = "".join(row["id"] + "\t" + base64.b64encode(row["text"].encode()).decode() + "\n" for row in rows)
result = subprocess.run(build["java_command"], input=framed, text=True, capture_output=True, timeout=90)
args.output.with_suffix(".stderr.log").write_text(result.stderr)
if result.returncode != 0:
    args.output.write_text(json.dumps({"state": "process_failed", "exit": result.returncode,
        "input_sha256": hashlib.sha256(args.inputs.read_bytes()).hexdigest(),
        "source_build": build["source_sha256"],
        "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest()}, indent=2) + "\n")
    raise RuntimeError("Probe failed; exact private stderr and structured failure receipt retained.")
cases = []
decode = lambda value: base64.b64decode(value).decode()
for row, line in zip(rows, result.stdout.splitlines(), strict=True):
    fields = line.split("\t")
    assert fields[0] == row["id"]
    pieces = []
    for part in fields[6].split(";") if fields[6] else []:
        item = part.split(",")
        pieces.append({"startUTF16": int(item[0]), "endUTF16": int(item[1]),
                       "source": decode(item[2]), "rendered": decode(item[3]),
                       "kind": item[4], "insertedSeparator": item[5] == "true"})
    raw = row["text"].encode("utf-16-le")
    for piece in pieces:
        assert raw[piece["startUTF16"]*2:piece["endUTF16"]*2].decode("utf-16-le") == piece["source"]
        if piece["kind"] != "converted":
            assert piece["rendered"] == piece["source"]
    if pieces:
        assert "".join(piece["source"] for piece in pieces) == row["text"]
    reading = None if fields[1] == "-" else decode(fields[1])
    cases.append({"id": row["id"], "source": row["text"], "expected_guard": row["expected_guard"],
                  "reading": reading, "inspection": decode(fields[2]),
                  "issues": fields[3].split(",") if fields[3] else [],
                  "first_ns": int(fields[4]), "warm_ns": int(fields[5]),
                  "guard_matches": (row["expected_guard"] == "reading") == (reading is not None),
                  "pieces": pieces})
report = {"input_sha256": hashlib.sha256(args.inputs.read_bytes()).hexdigest(),
          "source_build": build["source_sha256"], "platform": "Host JVM21; not Android device",
          "warm_exact_assertion": True, "exact_source_and_literals_checked": True, "cases": cases}
args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"cases": len(cases), "guard_matches": sum(case["guard_matches"] for case in cases),
                  "capture_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                  "maximum_first_ms": max(case["first_ns"] for case in cases)/1e6,
                  "maximum_warm_ms": max(case["warm_ns"] for case in cases)/1e6}))
raise SystemExit(0 if all(case["guard_matches"] for case in cases) else 1)
