#!/usr/bin/env python3
"""Collect a complete public-corpus iOS QA report and verify its remote transfer.

Run on the Mac after the native test finishes. No account/session data is read.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import platform
import re
import shlex
import subprocess


def preserve(path, data):
    if path.exists():
        if path.read_bytes() != data:
            raise RuntimeError(f"Preserve existing evidence: {path.name}")
        return
    with path.open("xb") as output:
        output.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report")
    parser.add_argument("--simulator", default="46CB569D-EA59-40E3-82CC-F4A0F36EDB87")
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()
    assert platform.system() == "Darwin"
    assert re.fullmatch(r"(?:bilingual|context)-ios-[a-z0-9-]+\.json", args.report)
    container = Path(subprocess.check_output(["xcrun", "simctl", "get_app_container", args.simulator,
                                             "co.fallsoft.vipi", "data"], text=True).strip())
    raw = (container / "Documents" / args.report).read_bytes()
    report = json.loads(raw)
    pairs = report["results"]
    assert len(pairs) == 90 and len({(p["source"], p["target"]) for p in pairs}) == 90
    assert all(p["status"] == "executed" and all(s["status"] == "executed" for s in p["samples"]) for p in pairs)
    count = sum(len(p["samples"]) for p in pairs)
    assert count in (540, 2880)
    output = Path(__file__).resolve().parents[1] / "artifacts"
    output.mkdir(exist_ok=True)
    receipt = {"file": args.report, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
               "pairs": 90, "samples": count, "evidence": report["evidence"],
               "native_alignment_policy": report.get("native_alignment_policy")}
    preserve(output / args.report, raw)
    compressed = output / (args.report + ".gz")
    manifest = output / (args.report + ".transfer.json")
    preserve(compressed, gzip.compress(raw, mtime=0))
    preserve(manifest, (json.dumps(receipt, indent=2) + "\n").encode())
    if args.upload:
        key = str(Path.home() / ".ssh/ozzz-aosp-hetzner-ed25519")
        host = "aosp@100.80.115.54"
        subprocess.run(["scp", "-i", key, str(compressed), str(manifest),
                        host + ":/aosp/development/vipi/artifacts/"], check=True)
        verification = """
import gzip,hashlib,json,pathlib,sys,os
root=pathlib.Path('/aosp/development/vipi/artifacts')
name=sys.argv[1]
receipt=json.loads((root/(name+'.transfer.json')).read_text())
raw=gzip.decompress((root/(name+'.gz')).read_bytes())
assert len(raw)==receipt['bytes'] and hashlib.sha256(raw).hexdigest()==receipt['sha256']
assert len(json.loads(raw)['results'])==90
dest=root/name
if dest.exists():
    assert dest.read_bytes()==raw, 'Preserve existing canonical evidence'
else:
    temporary=root/(name+'.verified-part')
    with temporary.open('xb') as output: output.write(raw)
    os.replace(temporary,dest)
print(json.dumps({'file':name,'sha256_verified':True,'pairs':90}))
"""
        subprocess.run(["ssh", "-i", key, host, shlex.join(["python3", "-c", verification, args.report])], check=True)
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
