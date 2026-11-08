"""Compare the native Kotlin port with ICU executing the pinned upstream rules.

This finite orthographic check is not conversational or pronunciation accuracy.
The matrix is specified before execution and no output is used to author rules.
"""
from pathlib import Path
import argparse
import base64
import hashlib
import json
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument("build_receipt", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
assert not args.output.exists()
build = json.loads(args.build_receipt.read_text())
texts = [chr(cp) for cp in range(0xAC00, 0xD7A4)]
for leading in (0, 11):
    for medial in range(21):
        for trailing in range(28):
            first = chr(0xAC00 + leading * 588 + medial * 28 + trailing)
            for second_leading in range(19):
                for second_medial in range(21):
                    texts.append(first + chr(0xAC00 + second_leading * 588 + second_medial * 28))
assert len(texts) == 480396
plain = "\n".join(texts) + "\n"
framed = "".join(f"{i}\t{base64.b64encode(text.encode()).decode()}\n" for i, text in enumerate(texts))
freeze = {
    "matrix": "All11172 modern syllables; every21vowel×28coda×19next-onset×21next-vowel for first onset g and silent ieung.",
    "cases": len(texts), "input_sha256": hashlib.sha256(plain.encode()).hexdigest(),
    "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "build_source_hashes": build["source_sha256"],
    "no_population_or_acoustic_claim": True,
}
freeze_path = args.output.with_suffix(".freeze.json")
assert not freeze_path.exists()
freeze_path.write_text(json.dumps(freeze, indent=2) + "\n")
started = time.monotonic()
upstream = subprocess.run(build["upstream_command"], input=plain, text=True, capture_output=True, timeout=120)
assert upstream.returncode == 0, upstream.stderr
upstream_seconds = time.monotonic() - started
started = time.monotonic()
native = subprocess.run(build["java_command"] + ["letters"], input=framed, text=True, capture_output=True, timeout=120)
assert native.returncode == 0, native.stderr
native_seconds = time.monotonic() - started
actual = []
for index, line in enumerate(native.stdout.splitlines()):
    identifier, encoded = line.split("\t")
    assert int(identifier) == index
    actual.append(base64.b64decode(encoded).decode())
expected = upstream.stdout.splitlines()
assert len(actual) == len(expected) == len(texts)
differences = []
count = 0
for source, want, got in zip(texts, expected, actual):
    if want != got:
        count += 1
        if len(differences) < 200:
            differences.append({"source": source, "upstream": want, "kotlin": got})
report = {**freeze, "mismatches": count, "examples": differences,
          "upstream_output_sha256": hashlib.sha256(upstream.stdout.encode()).hexdigest(),
          "kotlin_output_sha256": hashlib.sha256(("\n".join(actual) + "\n").encode()).hexdigest(),
          "upstream_seconds": upstream_seconds, "kotlin_seconds": native_seconds,
          "platform": "Host ICU74.2/JVM21, not Android device execution"}
args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({k: v for k, v in report.items() if k not in ("examples", "build_source_hashes")}))
raise SystemExit(1 if count else 0)
