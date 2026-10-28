#!/usr/bin/env python3
"""Compare the exact same native conversation inputs; expose gains and losses."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def identity(row):
    return tuple(row[k] for k in ("dataset","id","source","target"))

def encoded(span):
    return json.dumps(span,ensure_ascii=False,sort_keys=True)

def compare(args):
    inputs=json.loads(args.cases.read_text())
    cases={identity(r):r for r in inputs}
    assert len(cases)==len(inputs)
    before,after=[json.loads(p.read_text()) for p in [args.before,args.after]]
    for report in [before,after]:
        assert report["schema"]=="vipi-bundled-conversation-replay-1"
        assert report["complete"] and not report["failures"]
        assert report["cases_sha256"]==sha(args.cases)
        assert len(report["outcomes"])==len(cases)
    assert before["platform"]==after["platform"]
    old,new=[{identity(r):r for r in report["outcomes"]} for report in [before,after]]
    assert old.keys()==new.keys()==cases.keys()
    changes=[];counts=Counter();groups=defaultdict(Counter)
    for key,case in cases.items():
        left,right=old[key],new[key]
        for row in [left,right]:
            assert row["original"]==case["original"] and row["translation"]==case["translation"]
        a,b=left["combined_spans"],right["combined_spans"]
        added=[s for s in b if encoded(s) not in {encoded(x) for x in a}]
        removed=[s for s in a if encoded(s) not in {encoded(x) for x in b}]
        regression=any(k in case for k in ["forbidden_source","expected_source"])
        for group in ["all", "regression" if regression else "ordinary",
                      case["source"]+"-"+case["target"],"dataset:"+case["dataset"]]:
            counter=groups[group]
            counter["cases"]+=1
            counter["before_nonempty"]+=bool(a)
            counter["after_nonempty"]+=bool(b)
            counter["before_spans"]+=len(a)
            counter["after_spans"]+=len(b)
            counter["added_spans"]+=len(added)
            counter["removed_spans"]+=len(removed)
        if added or removed:
            counts["changed_messages"]+=1
            counts["added_spans"]+=len(added)
            counts["removed_spans"]+=len(removed)
            counts["newly_nonempty"]+=int(not a and bool(b))
            counts["newly_empty"]+=int(bool(a) and not b)
            changes.append(dict(identity=key,original=case["original"],translation=case["translation"],
                added=added,removed=removed,regression=regression))
    result=dict(schema="vipi-bundled-replay-changes-1",complete=True,
        cases_sha256=sha(args.cases),before_sha256=sha(args.before),after_sha256=sha(args.after),
        before_catalog_sha256=before["bundled_catalog_sha256"],
        after_catalog_sha256=after["bundled_catalog_sha256"],platform=after["platform"],
        groups={k:dict(v) for k,v in sorted(groups.items())},counts=dict(counts),changes=changes,
        independent_semantic_acceptance=False,population_coverage_claim=False)
    with args.output.open("x") as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2);stream.write("\n")
    print(json.dumps({k:result[k] for k in ["platform","counts","before_catalog_sha256","after_catalog_sha256"]}))
    print(json.dumps({k:result["groups"][k] for k in ["all","ordinary","regression"] if k in result["groups"]}))

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ["cases","before","after","output"]:
        parser.add_argument("--"+name,type=Path,required=True)
    compare(parser.parse_args())
