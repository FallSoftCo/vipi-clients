#!/usr/bin/env python3
"""Bounded English–Spanish evaluation of complete present forms; no promotion."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib,json,os,shutil,subprocess
ROOT=Path("/aosp/development/vipi")
OUT=ROOT/"artifacts/present-verb-context-pilot-001"
SNAP=OUT/"compiler-source"
PY=ROOT/".venv-lexical-context/bin/python"
SOURCES={"tatoeba":("conversation-corpus-002",2*1024**3),
         "pgv":("parallel-global-voices-001",2*1024**3),
         "massive":("massive-corpus-003",512*1024**2)}
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+"\n")
def stage(name):
    corpus_name,peak=SOURCES[name]
    original=ROOT/"artifacts"/corpus_name
    working=ROOT/"artifacts/swahili-context-release-002"/("working-"+name)
    pin=json.loads((original/"receipt.json").read_text())
    retained=json.loads((working/"working-copy-receipt.json").read_text())
    assert retained["verified"] and not retained["retired_after_build"]
    assert sha(working/"corpus.sqlite")==pin["sha256"]==retained["sha256"]
    assert sha(working/"receipt.json")==sha(original/"receipt.json")
    output=ROOT/"artifacts"/("lexical-contexts-present-pilot-001-"+name)
    command=[str(PY),str(SNAP/"qa/immersion/build_lexical_contexts.py"),
        "--shards",str(ROOT/"artifacts/lexical-present-verbs-001"),
        "--corpus",str(working/"corpus.sqlite"),"--output",str(output),
        "--language","en","--language","es"]
    with (OUT/(name+".log")).open("x") as log:
        subprocess.run(["storage-build","--peak-bytes",str(peak),"--",*command],
            cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,check=True)
    r=json.loads((output/"receipt.json").read_text())
    assert r["complete"] and not r["pilot"] and set(r["languages"])=={"en","es"}
    return name,r
def main():
    catalog=ROOT/"artifacts/lexical-present-verbs-001/catalog.json"
    assert json.loads(catalog.with_name("receipt.json").read_text())["complete"]
    OUT.mkdir(exist_ok=False);SNAP.mkdir();files=[]
    for folder in ["language-packs","qa/immersion"]:
        for p in sorted((ROOT/folder).glob("*.py")):
            rel=p.relative_to(ROOT);dst=SNAP/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
            files.append(dict(path=str(rel),sha256=sha(dst)))
    save(SNAP/"receipt.json",dict(files=files))
    save(OUT/"plan.json",dict(owner="01a16e0d-ac69-7dd0-872a-8cf087160515",
        dictionary_catalog_sha256=sha(catalog),compiler_snapshot_sha256=sha(SNAP/"receipt.json"),
        languages=["en","es"],directions=2,production_promoted=False,
        admission_basis="Same verified source corpora on disk, no input copies. Each two-language context bounded by previous single-changed-language 2 GiB budgets; MASSIVE 512 MiB. Witness 2 GiB versus measured 1.16 GB observations for a previous batch containing all Korean directions and additional pairs.",
        semantic_accuracy_claim=False))
    results={}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(stage,name) for name in SOURCES]):
            name,r=f.result();results[name]=r
            print(json.dumps(dict(stage=name,bytes=r["bytes"],counts=r["counts"])),flush=True)
    command=[str(PY),str(SNAP/"language-packs/build_context_witnesses.py"),
        "--contexts",str(ROOT/"artifacts/lexical-contexts-present-pilot-001-tatoeba/contexts.sqlite"),
        "--additional-context",str(ROOT/"artifacts/lexical-contexts-present-pilot-001-pgv/contexts.sqlite"),
        "--additional-corpus-receipt",str(ROOT/"artifacts/parallel-global-voices-001/receipt.json"),
        "--extra-context",str(ROOT/"artifacts/lexical-contexts-present-pilot-001-massive/contexts.sqlite"),
        "--extra-corpus-receipt",str(ROOT/"artifacts/massive-corpus-003/receipt.json"),
        "--source-exclusions",str(ROOT/"artifacts/corpus-exclusions-001/hashes.sqlite"),
        "--output",str(ROOT/"artifacts/context-witnesses-present-pilot-001"),
        "--pair","en-es","--pair","es-en"]
    with (OUT/"witness.log").open("x") as log:
        subprocess.run(["storage-build","--peak-bytes",str(2*1024**3),"--",*command],
            cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,check=True)
    witness=ROOT/"artifacts/context-witnesses-present-pilot-001/receipt.json"
    w=json.loads(witness.read_text());assert w["complete"]
    save(OUT/"receipt.json",dict(complete=True,dictionary_catalog_sha256=sha(catalog),
        contexts={n:r["sha256"] for n,r in results.items()},witness_receipt_sha256=sha(witness),
        counts=w["counts"],native_qualified=False,production_promoted=False))
    print("Present-form English–Spanish context evaluation data complete.",flush=True)
if __name__=="__main__":main()
