#!/usr/bin/env python3
"""Compare actual selected spans; never substitute phrase-only baseline counters."""
import argparse,hashlib,json
from collections import defaultdict
from pathlib import Path
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def selected(row):
    return row["combined_spans"] if "combined_spans" in row else row["spans"]
def case_key(row):
    return tuple(row[field] for field in ("id","source","target"))
def check_report(report,allow_failures=False):
    assert report["complete"]
    if not allow_failures:
        if "passed" in report:assert report["passed"]
        assert not report.get("failures")
    if report.get("schema")=="vipi-bundled-conversation-replay-1":
        assert all(row["baseline_retained"] for row in report["outcomes"])

def identity(span):return tuple(span.get(k) for k in ["source","target","start","end","target_start","target_end","reading"])
def compare(args):
    cases=json.loads(args.cases.read_text());fixtures={case_key(c):c for c in cases};assert len(fixtures)==len(cases)
    reports=[json.loads(path.read_text()) for path in [args.baseline,args.candidate]]
    for index,report in enumerate(reports):check_report(report,index==0 and args.allow_baseline_failures)
    tables=[]
    for report in reports:
        # Old lexical reports carry only id. It is safe only when the
        # fixture id itself is unique; bundled reports require the direction.
        by_id={c["id"]:c for c in cases}
        rows=[]
        for row in report["outcomes"]:
            if "source" not in row or "target" not in row:
                assert len(by_id)==len(cases), "Report lacks direction for repeated IDs"
                fixture=by_id[row["id"]]
                row={**row,"source":fixture["source"],"target":fixture["target"]}
            rows.append(row)
        tables.append({case_key(row):row for row in rows})
    assert all(set(t)==set(fixtures) and len(t)==len(r["outcomes"]) for t,r in zip(tables,reports))
    groups=defaultdict(lambda:dict(cases=0,before_messages=0,after_messages=0,before_spans=0,after_spans=0,added_spans=0,removed_spans=0))
    changed=[]
    for case in cases:
        identifier=case_key(case);before,after=[selected(t[identifier]) for t in tables]
        for span in before+after:
            for field,start,end,word in [("original","start","end","source"),("translation","target_start","target_end","target")]:
                text=case[field].encode("utf-16-le")
                assert 0<=span[start]<span[end]<=len(text)//2
                assert text[2*span[start]:2*span[end]].decode("utf-16-le")==span[word]
        old={identity(s):s for s in before};new={identity(s):s for s in after}
        assert len(old)==len(before) and len(new)==len(after)
        added=[new[k] for k in sorted(new.keys()-old.keys(),key=str)]
        removed=[old[k] for k in sorted(old.keys()-new.keys(),key=str)]
        for group in ["all",case["dataset"]+":"+case["source"]+"-"+case["target"]]:
            g=groups[group];g["cases"]+=1;g["before_messages"]+=bool(before);g["after_messages"]+=bool(after)
            g["before_spans"]+=len(before);g["after_spans"]+=len(after);g["added_spans"]+=len(added);g["removed_spans"]+=len(removed)
        if added or removed:changed.append(dict(case=case,before=before,after=after,added=added,removed=removed))
    args.output.mkdir(exist_ok=False,parents=True)
    (args.output/"changes.json").write_text(json.dumps(changed,ensure_ascii=False,indent=2)+"\n")
    receipt=dict(complete=True,baseline_report_sha256=sha(args.baseline),candidate_report_sha256=sha(args.candidate),
        cases_sha256=sha(args.cases),compiler_sha256=sha(Path(__file__)),changes_sha256=sha(args.output/"changes.json"),
        groups=dict(groups),changed_messages=len(changed),baseline_failures=reports[0].get("failures",[]),semantic_accuracy_claim=False,production_promoted=False)
    (args.output/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps({key:receipt[key] for key in ("complete","changed_messages","baseline_failures")} | {"all":receipt["groups"]["all"]}),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ["cases","baseline","candidate","output"]:p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--allow-baseline-failures",action="store_true",help="Compare a known failing old reader; candidate must still pass. Failures remain in receipt.")
    compare(p.parse_args())
