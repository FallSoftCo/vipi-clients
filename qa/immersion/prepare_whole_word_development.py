#!/usr/bin/env python3
"""Freeze a small stratified conversation cohort for a matcher experiment.
Not an unseen acceptance set or a population coverage estimate.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from prepare_noun_geometry import sha

def main(a):
    manifest=json.loads((a.base/"manifest.json").read_text())
    assert sha(a.base/"cases.json")==manifest["cases_sha256"]
    rows=json.loads((a.base/"cases.json").read_text())
    groups=defaultdict(set)
    datasets={"sms","multi3woz","xpersona","liva-sw-explicit-replay"}
    for r in rows:
        if r["dataset"] in datasets: groups[(r["dataset"],r["source"])].add(r["id"])
    chosen={k:set(sorted(ids,key=lambda i:hashlib.sha256(("whole-word-development-1:"+i).encode()).hexdigest())[:4]) for k,ids in groups.items()}
    selected=[r for r in rows if r["id"] in chosen.get((r["dataset"],r["source"]),set())]
    # Keep observed semantic failures as a separate section. Do not import
    # authored abstention expectations that only encode the former algorithm.
    negatives=[r for r in rows if "forbidden_source" in r and not r["dataset"].startswith("authored-")]
    keys={(r["dataset"],r["id"],r["source"],r["target"]) for r in selected}
    selected += [r for r in negatives if (r["dataset"],r["id"],r["source"],r["target"]) not in keys]
    a.output.mkdir(parents=True,exist_ok=False)
    for shard in manifest["shards"]:
        source=a.base/(shard["language"]+".sqlite")
        assert source.stat().st_size==shard["bytes"]
        (a.output/source.name).symlink_to(source.resolve())
    for name in ("evaluation-exclusions.sqlite","EVALUATION-NOTICE.txt","LICENSE-FLORES-200.txt"):
        if (a.base/name).exists(): (a.output/name).symlink_to((a.base/name).resolve())
    target=a.output/"cases.json"
    target.write_text(json.dumps(selected,ensure_ascii=False,separators=(",",":"))+"\n")
    manifest.update(cases=len(selected),cases_sha256=sha(target),datasets=dict(Counter(r["dataset"] for r in selected)),
        prior_manifest_sha256=sha(a.base/"manifest.json"),compiler_sha256=sha(Path(__file__)),
        evaluation_scope="targeted-regression-only",
        development_selection={"method":"First four source identities per dataset/source stratum ordered by fixed salted SHA-256; all existing target directions; additional retained observed semantic negatives.",
          "source_identities":[{"dataset":k[0],"source":k[1],"ids":sorted(v)} for k,v in sorted(chosen.items())],
          "conversation_source_turns":sum(map(len,chosen.values())),"coverage_denominator_eligible":False,
          "translation_reused":True,"independent_semantic_acceptance":False})
    (a.output/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"cases":len(selected),"turns":sum(map(len,chosen.values())),"retained_negative_cases":len(negatives)}))
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    main(p.parse_args())
