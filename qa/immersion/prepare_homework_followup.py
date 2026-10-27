#!/usr/bin/env python3
"""Select all source cases affected by the homework guard plus retained regressions."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
from prepare_noun_geometry import sha

# Same source-only scope as the native guard. This is a regression selection,
# never a new conversational coverage denominator.
HOME_WORK=re.compile(r"(?<![\w])home\s+works?(?![\w])",re.I)

def main(a):
    manifest=json.loads((a.base/"manifest.json").read_text())
    assert sha(a.base/"cases.json")==manifest["cases_sha256"]
    full=json.loads((a.base/"cases.json").read_text())
    selected=[];affected=[]
    for row in full:
        match=row["source"]=="en" and bool(HOME_WORK.search(row["original"]))
        if match:
            affected.append({k:row[k] for k in ("dataset","id","source","target")})
        if match or "expected_source" in row or "forbidden_source" in row or row["dataset"].startswith("authored-"):
            selected.append(row)
    assert affected and len(selected)<len(full)
    manifest.update(cases=len(selected),datasets=dict(Counter(r["dataset"] for r in selected)),
        prior_manifest_sha256=sha(a.base/"manifest.json"),compiler_sha256=sha(Path(__file__)),
        evaluation_scope="targeted-regression-only",
        targeted_scope=dict(source_population_cases=len(full),source_manifest_sha256=sha(a.base/"manifest.json"),
            all_affected_cases=affected,selection="All English home work/home works matches, all required-positive/known-negative cases, and all authored behavior cases.",
            coverage_denominator_eligible=False))
    a.output.mkdir(parents=True,exist_ok=False)
    for shard in manifest["shards"]:
        source=a.base/(shard["language"]+".sqlite")
        assert source.stat().st_size==shard["bytes"]
        (a.output/source.name).symlink_to(source.resolve())
    for name in ("diagnostic-receipt.json","evaluation-exclusions.sqlite","EVALUATION-NOTICE.txt","LICENSE-FLORES-200.txt"):
        if (a.base/name).exists():
            (a.output/name).symlink_to((a.base/name).resolve())
    path=a.output/"cases.json"
    path.write_text(json.dumps(selected,ensure_ascii=False,separators=(",",":"))+"\n")
    manifest["cases_sha256"]=sha(path)
    (a.output/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(dict(cases=len(selected),affected=len(affected),manifest_sha256=sha(a.output/"manifest.json"))))

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    main(p.parse_args())

