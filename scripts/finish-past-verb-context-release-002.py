#!/usr/bin/env python3
"""Finish the pinned past-verb build in bounded, disjoint pair batches."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import importlib.util,itertools,json,os,time
from pathlib import Path
ROOT=Path("/aosp/development/vipi")
spec=importlib.util.spec_from_file_location("release",ROOT/"scripts/build-past-verb-context-release-002.py")
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
def checked(folder):
    folder=Path(folder);receipt=json.loads((folder/"receipt.json").read_text())
    assert receipt["complete"] and receipt["sha256"]==R.sha(folder/"witnesses.sqlite")
    return receipt
def retire(path,reason,successor):
    path=Path(path)
    record=dict(file=str(path),sha256=R.sha(path),bytes=path.stat().st_size,reason=reason,
        successor_sha256=successor,complete=False)
    destination=path.with_name(path.name+".retirement.json")
    assert not destination.exists();R.write(destination,record)
    path.unlink();record["complete"]=True;R.write(destination,record)
def batch(row):
    name=row["revision"];folder=ROOT/"artifacts"/name
    command=[R.SNAPSHOT/"language-packs/build_context_witnesses.py",
        "--contexts",ROOT/"artifacts/lexical-contexts-past-review-002/contexts.sqlite",
        "--additional-context",ROOT/"artifacts/lexical-contexts-pgv-past-review-002/contexts.sqlite",
        "--additional-corpus-receipt",ROOT/"artifacts/parallel-global-voices-001/receipt.json",
        "--extra-context",ROOT/"artifacts/lexical-contexts-massive-past-review-002/contexts.sqlite",
        "--extra-corpus-receipt",ROOT/"artifacts/massive-corpus-003/receipt.json",
        "--source-exclusions",ROOT/"artifacts/corpus-exclusions-001/hashes.sqlite",
        "--base-supplement-receipt",ROOT/"artifacts/swahili-corpus-001/receipt.json","--output",folder]
    for pair in row["pairs"]:command+=["--pair",pair]
    R.guarded(name,row["peak_bytes"],command)
    receipt=checked(folder);assert set(receipt["requested_pairs"])==set(row["pairs"])
    observations=folder/"observations.sqlite"
    assert R.sha(observations)==receipt["observations_sha256"]
    retire(observations,"Completed compiler closed SQLite. Exact contexts and compiler, witness counts and attributed examples retained.",receipt["sha256"])
    print(json.dumps(dict(stage="witness_batch_complete",revision=name,rules=receipt["counts"]["witnesses"])),flush=True)
def main():
    os.chdir(ROOT);R.verify()
    catalog=ROOT/"artifacts/lexical-shards-019/catalog.json"
    # These two context jobs were already running. Wait for their exact receipts;
    # do not repeat the jobs if their completion is uncertain.
    deadline=time.monotonic()+7200
    for name in ["tatoeba","pgv"]:
        marker=ROOT/"artifacts"/R.SOURCES[name]["output"]/"receipt.json"
        while not marker.exists():
            assert time.monotonic()<deadline,"Preserved context stage incomplete"
            time.sleep(10)
        row=json.loads(marker.read_text())
        assert row["complete"] and row["source_catalog_sha256"]==R.sha(catalog)
    massive=ROOT/"artifacts"/R.SOURCES["massive"]["output"]
    if not massive.exists():
        R.guarded(massive.name,R.SOURCES["massive"]["peak"],[R.SNAPSHOT/"driver.py","--context-stage","massive"])
    else:
        while not (massive/"receipt.json").exists():
            assert time.monotonic()<deadline,"Previously started MASSIVE stage incomplete"
            time.sleep(10)
    contexts=[json.loads((ROOT/"artifacts"/row["output"]/"receipt.json").read_text()) for row in R.SOURCES.values()]
    assert all(c["complete"] and c["source_catalog_sha256"]==R.sha(catalog) for c in contexts)
    unordered=["-".join(pair) for pair in itertools.combinations(R.LANGUAGES,2) if {"en","ja","ko"}&set(pair)]
    counts={pair:sum(c["pairs"].get(pair,0) for c in contexts) for pair in unordered}
    groups=[];group=[];total=0
    for pair,count in sorted(counts.items(),key=lambda row:row[1],reverse=True):
        if group and total+count>2400000:groups.append(group);group=[];total=0
        group.append(pair);total+=count
    if group:groups.append(group)
    groups.reverse();rows=[]
    for number,group in enumerate(groups,1):
        count=sum(counts[p] for p in group)
        rows.append(dict(revision=f"context-witnesses-past-002-batch-{number:03d}",
            pairs=sorted(d for p in group for d in (p,"-".join(reversed(p.split("-"))))),
            candidate_alignments=count,peak_bytes=(6 if count>2400000 else 4)*1024**3))
    R.write(R.OUTPUT/"bounded-witness-plan.json",dict(controller_sha256=R.sha(Path(__file__)),batches=rows,
        contexts_sha256=[c["sha256"] for c in contexts],frozen_compilers_sha256=R.sha(R.SNAPSHOT/"receipt.json"),
        basis="Existing agreement batch009 processed 2.77M distinct references using 2.92 GB observations; same measured 4/6 GiB batch admission as scripts/build-context-agreement-001.py.",
        automatic_retries=False))
    with ThreadPoolExecutor(max_workers=2) as pool:
        for job in as_completed([pool.submit(batch,row) for row in reversed(rows)]):job.result()
    parent=ROOT/"artifacts"/rows[0]["revision"]
    for number,row in enumerate(rows[1:],1):
        target=ROOT/"artifacts"/f"context-witnesses-past-002-merge-{number:03d}"
        R.guarded(target.name,2*1024**3,[R.SNAPSHOT/"language-packs/replace_context_witness_pairs.py",
            "--base",parent/"witnesses.sqlite","--replacement",ROOT/"artifacts"/row["revision"]/"witnesses.sqlite",
            "--output",target])
        result=checked(target)
        if "-merge-" in parent.name:
            retire(parent/"witnesses.sqlite","Superseded cumulative merge; original batch witnesses and receipts retained.",result["sha256"])
        parent=target
    replacement=ROOT/"artifacts/context-witnesses-past-review-002";replacement.mkdir(exist_ok=False)
    for name in ["witnesses.sqlite","receipt.json","ATTRIBUTION.txt"]:os.link(parent/name,replacement/name)
    compiled=checked(replacement)
    expected={a+"-"+b for a in R.LANGUAGES for b in R.LANGUAGES if a!=b and {"en","ja","ko"}&{a,b}}
    assert set(compiled["requested_pairs"])==expected and len(expected)==54
    command=[R.SNAPSHOT/"language-packs/replace_context_witness_pairs.py",
        "--base",ROOT/"artifacts/context-witnesses-018/witnesses.sqlite",
        "--replacement",replacement/"witnesses.sqlite","--output",ROOT/"artifacts/context-witnesses-019",
        "--dictionary-baseline",ROOT/"artifacts/lexical-shards-018/catalog.json","--dictionary-catalog",catalog]
    for row in R.SOURCES.values():
        command+=["--base-context-receipt",ROOT/"artifacts"/row["base"]/"receipt.json",
            "--replacement-context-receipt",ROOT/"artifacts"/row["output"]/"receipt.json"]
    for revision in ["lexical-contexts-swahili-review-002","lexical-contexts-pgv-swahili-review-002",
        "lexical-contexts-massive-swahili-review-002","lexical-contexts-arabic-review-002",
        "lexical-contexts-pgv-arabic-review-002","lexical-contexts-massive-arabic-review-002"]:
        command+=["--base-context-receipt",ROOT/"artifacts"/revision/"receipt.json"]
    for revision in [f"context-witnesses-agreement-batch-{i:03d}" for i in range(1,10)]+[
        "context-witnesses-swahili-review-002","context-witnesses-arabic-review-002"]:
        command+=["--base-pair-receipt",ROOT/"artifacts"/revision/"receipt.json"]
    R.guarded("context-witnesses-019",2*1024**3,command)
    R.guarded("context-pair-packs-019",512*1024**2,[R.SNAPSHOT/"language-packs/export_context_pair_packs.py",
        "--source",ROOT/"artifacts/context-witnesses-019/witnesses.sqlite","--catalog",catalog,
        "--output",ROOT/"artifacts/context-pair-packs-019"])
    R.guarded("bundled-lexical-008",768*1024**2,[R.SNAPSHOT/"language-packs/bundle_lexical_data.py",
        "--base",catalog,"--catalog",catalog,"--contexts",ROOT/"artifacts/context-pair-packs-019/catalog.json",
        "--output",ROOT/"artifacts/bundled-lexical-008"])
    bundle=ROOT/"artifacts/bundled-lexical-008/catalog.json";meta=json.loads(bundle.read_text())
    assert meta["directed_pairs"]==110
    R.write(R.OUTPUT/"receipt.json",dict(complete=True,bundle_sha256=R.sha(bundle),
        dictionary_catalog_sha256=R.sha(catalog),
        recomputation_proof_sha256=R.sha(ROOT/"artifacts/context-witnesses-019/recomputation-proof.json"),
        changed_directions=54,total_directions=110,compressed_bytes=meta["compressed_bytes"],
        native_qualified=False,semantic_accuracy_claim=False,finish_controller_sha256=R.sha(Path(__file__))))
    print("Past-verb bundle complete; native qualification required.",flush=True)
if __name__=="__main__":main()
