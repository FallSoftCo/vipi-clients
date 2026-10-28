#!/usr/bin/env python3
"""Append exact authored case/name probes to an explicitly pinned baseline."""
import argparse,hashlib,json,os
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--baseline",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    baseline=args.baseline/"cases.json";manifest=args.baseline/"manifest.json"
    assert sha(baseline)=="32540e64fde613067bae1b6a7d5e43e33783d9b057453deb686e70cc2dd9af26"
    extra=Path(__file__).with_name("repeated-unit-regressions.json")
    cases=json.loads(baseline.read_text())+json.loads(extra.read_text())
    assert len({(r["id"],r["source"],r["target"]) for r in cases})==len(cases)
    args.output.mkdir(exist_ok=False,parents=True)
    data=args.output/"cases.json";data.write_text(json.dumps(cases,ensure_ascii=False,indent=2)+chr(10))
    pin=json.loads(manifest.read_text())
    pin.update(cases=len(cases),cases_sha256=sha(data),baseline_fixture_sha256=sha(baseline),
        authored_repeated_unit_cases=6,authored_cases_sha256=sha(extra),compiler_sha256=sha(Path(__file__)),
        development_expectation="Balanced repeated whole units and count, number, name counterexamples; authored probes, not coverage evidence.")
    (args.output/"manifest.json").write_text(json.dumps(pin,indent=2)+chr(10))
    for row in pin["shards"]:
        name=row["language"]+".sqlite"
        (args.output/name).symlink_to(os.path.relpath((args.baseline/name).resolve(),args.output.resolve()))
    print(json.dumps(dict(cases=len(cases),cases_sha256=sha(data))),flush=True)
if __name__=="__main__":main()
