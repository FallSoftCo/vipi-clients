#!/usr/bin/env python3
"""Expose statistical alignment proposals on existing public development inputs."""
import argparse
from collections import Counter,defaultdict
from contextlib import closing
import hashlib,json,math,re,sqlite3,subprocess
from pathlib import Path
from prepare_statistical_alignment_pilot import tokenize
from conversation_corpus import sha_file,write_json

def identity(r):return tuple(r[k] for k in ["dataset","id","source","target"])
def build(a):
    models=json.loads((a.models/"receipt.json").read_text())
    assert models["complete"]
    a.output.mkdir(exist_ok=False)
    grouped=defaultdict(list)
    cases=json.loads(a.cases.read_text())
    for r in cases:
        pair="-".join(sorted([r["source"],r["target"]]))
        if pair in {"en-es","en-sw"}:grouped[pair].append(r)
    for pair,rows in grouped.items():
        rows.sort(key=lambda r:hashlib.sha256(json.dumps(identity(r)).encode()).hexdigest())
        grouped[pair]=rows[:a.maximum]
    results=[];counts=Counter()
    for pair,rows in sorted(grouped.items()):
        tokens=[]
        for r in rows:
            text=[r["original"],r["translation"]]
            if r["source"]!="en":text.reverse()
            tokens.append([tokenize(v) for v in text])
        input_path=a.output/(pair+".txt")
        input_path.write_text("".join(" ||| ".join(" ".join(t[0].casefold() for t in side) for side in sides)+"\n" for sides in tokens))
        aligned=[];tables=[]
        for direction in ["forward","reverse"]:
            prefix=a.models/(pair+"-"+direction)
            expected=next(r for r in models["models"] if r["pair"]==pair and r["reverse"]==(direction=="reverse"))
            params=prefix.with_suffix(".params");log=prefix.with_suffix(".log")
            assert sha_file(params)==expected["files"][params.name]["sha256"]
            lines=log.read_text().splitlines()
            mean=next(l.split()[-1] for l in lines if "expected target length" in l)
            tension=next(l.split()[-1] for l in lines if "final tension" in l)
            command=[str((a.toolchain/"build/fast_align").resolve()),"-i",str(input_path),"-d","-T",tension,"-m",mean,"-f",str(params)]
            if direction=="reverse":command.append("-r")
            run=subprocess.run(command,capture_output=True,text=True,check=True,stdin=subprocess.DEVNULL)
            (a.output/(pair+"-"+direction+".output")).write_text(run.stdout)
            (a.output/(pair+"-"+direction+".log")).write_text(run.stderr)
            parsed=[{tuple(map(int,point.split("-"))) for point in l.split("|||")[2].split()} for l in run.stdout.splitlines()]
            assert len(parsed)==len(rows);aligned.append(parsed)
            table={}
            with params.open() as stream:
                for line in stream:
                    source,target,score=line.split()
                    table[(source,target)]=math.exp(float(score))
            tables.append(table)
        for i,(row,sides) in enumerate(zip(rows,tokens)):
            mutual=aligned[0][i]&aligned[1][i]
            source_counts=Counter(x for x,y in mutual);target_counts=Counter(y for x,y in mutual)
            proposals=[]
            for x,y in sorted(mutual):
                left,right=sides[0][x],sides[1][y]
                if source_counts[x]!=1 or target_counts[y]!=1:continue
                if not any(c.isalpha() for c in left[0]) or not any(c.isalpha() for c in right[0]):continue
                f=tables[0].get((left[0].casefold(),right[0].casefold()),0.0)
                b=tables[1].get((right[0].casefold(),left[0].casefold()),0.0)
                source,target=(left,right) if row["source"]=="en" else (right,left)
                proposals.append(dict(source=source[0],target=target[0],start=source[1],end=source[2],
                    target_start=target[1],target_end=target[2],forward_probability=f,reverse_probability=b,
                    minimum_probability=min(f,b)))
            results.append(dict(case=row,proposals=proposals))
            counts[pair+":cases"]+=1;counts[pair+":proposals"]+=len(proposals)
    write_json(a.output/"report.json",dict(complete=True,cases_sha256=sha_file(a.cases),
        model_receipt_sha256=sha_file(a.models/"receipt.json"),compiler_sha256=sha_file(Path(__file__)),
        tokenization_source_sha256=sha_file(Path(__file__).with_name("prepare_statistical_alignment_pilot.py")),
        offsets="Unicode code points, not native UTF-16",counts=dict(counts),results=results,
        selection_policy="One-to-one mutual forward/reverse proposal only; no probability threshold claimed as accuracy.",
        independent_semantic_acceptance=False,runtime_integrated=False))
    print(json.dumps(dict(counts=counts)))

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ["models","toolchain","cases","output"]:p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--maximum",type=int,default=120)
    build(p.parse_args())
