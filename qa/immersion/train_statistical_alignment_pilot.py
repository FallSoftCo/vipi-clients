#!/usr/bin/env python3
"""Train four bounded statistical alignment tables for authoring review only."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,subprocess,time
from pathlib import Path

def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()

def build(a):
    corpus=json.loads((a.corpus/"receipt.json").read_text())
    toolchain=json.loads((a.toolchain/"receipt.json").read_text())
    assert corpus["complete"] and toolchain["complete"]
    executable=(a.toolchain/"build/fast_align").resolve()
    assert sha(executable)==toolchain["binaries"]["fast_align"]["sha256"]
    for row in corpus["outputs"]:
        assert sha(a.corpus/(row["pair"]+".txt"))==row["text_sha256"]
    a.output.mkdir(exist_ok=False)
    def train(job):
        pair,reverse=job
        prefix=a.output/(pair+("-reverse" if reverse else "-forward"))
        parameters=prefix.with_suffix(".params")
        command=[str(executable),"-i",str(a.corpus/(pair+".txt")),"-d","-o","-v","-p",str(parameters)]
        if reverse:command.append("-r")
        start=time.monotonic()
        with prefix.with_suffix(".align").open("x") as out,prefix.with_suffix(".log").open("x") as err:
            result=subprocess.run(command,stdout=out,stderr=err,stdin=subprocess.DEVNULL)
        assert result.returncode==0,(pair,reverse,result.returncode)
        files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in
            [parameters,prefix.with_suffix(".align"),prefix.with_suffix(".log")]}
        row=dict(pair=pair,reverse=reverse,command=command,seconds=time.monotonic()-start,files=files)
        print(json.dumps(row),flush=True)
        return row
    jobs=[(r["pair"],reverse) for r in corpus["outputs"] for reverse in [False,True]]
    with ThreadPoolExecutor(max_workers=2) as pool:models=list(pool.map(train,jobs))
    receipt=dict(complete=True,models=models,corpus_receipt_sha256=sha(a.corpus/"receipt.json"),
        toolchain_receipt_sha256=sha(a.toolchain/"receipt.json"),driver_sha256=sha(Path(__file__)),
        runtime_integrated=False,independent_semantic_acceptance=False)
    (a.output/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ["corpus","toolchain","output"]:p.add_argument("--"+name,type=Path,required=True)
    build(p.parse_args())
