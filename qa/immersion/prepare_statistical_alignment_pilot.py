#!/usr/bin/env python3
"""Prepare a bounded authoring pilot from pinned development sentence pairs."""
import argparse
from collections import Counter
from contextlib import closing
import hashlib,heapq,json,re,sqlite3,time
from pathlib import Path
from build_corpus_exclusions import fingerprint
from conversation_corpus import sha_file,write_json

TOKEN=re.compile(r"[^\W_]+(?:['’][^\W_]+)*|[^\w\s]",re.UNICODE)
def tokenize(text):return [(m.group(),m.start(),m.end()) for m in TOKEN.finditer(text)]

def build(args):
    args.output.mkdir(exist_ok=False)
    excluded=set()
    evidence=[]
    for p in args.evaluation_exclusions:
        with closing(sqlite3.connect(p.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)) as d:
            excluded.update(x[0] for x in d.execute("SELECT digest FROM hashes"))
        evidence.append(dict(path=str(p),sha256=sha_file(p),kind="hash-index"))
    for p in args.evaluation_cases:
        for r in json.loads(p.read_text()):
            excluded.add(fingerprint(r["source"],r["original"]))
            excluded.add(fingerprint(r["target"],r["translation"]))
        evidence.append(dict(path=str(p),sha256=sha_file(p),kind="native-replay-input"))
    heaps={pair:[] for pair in ["en-es","en-sw"]}
    counts=Counter();sources=[];seen=set()
    for path in args.contexts:
        receipt=json.loads((path.parent/"receipt.json").read_text())
        assert receipt["complete"] and receipt["corpus_partition"]=="development"
        assert sha_file(path)==receipt["sha256"]
        sources.append(dict(path=str(path),sha256=receipt["sha256"],receipt_sha256=sha_file(path.parent/"receipt.json")))
        with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)) as db:
            db.execute("PRAGMA cache_size=-32768");db.execute("PRAGMA temp_store=FILE")
            query="""SELECT l.a,a.language,a.text,l.b,b.language,b.text
                FROM (SELECT DISTINCT a,b FROM alignments) l
                JOIN sentences a ON a.id=l.a JOIN sentences b ON b.id=l.b
                WHERE (a.language='en' AND b.language IN ('es','sw'))
                   OR (b.language='en' AND a.language IN ('es','sw'))"""
            for a,al,at,b,bl,bt in db.execute(query):
                if bl=="en":a,al,at,b,bl,bt=b,bl,bt,a,al,at
                pair="en-"+bl;counts[pair+":source_pairs"]+=1
                if fingerprint(al,at) in excluded or fingerprint(bl,bt) in excluded:
                    counts[pair+":evaluation_overlap"]+=1;continue
                left,right=tokenize(at),tokenize(bt)
                if not 2<=len(left)<=60 or not 2<=len(right)<=60 or "|||" in at or "|||" in bt:
                    counts[pair+":length_or_delimiter"]+=1;continue
                digest=hashlib.sha256(fingerprint(al,at)+fingerprint(bl,bt)).hexdigest()
                if digest in seen:counts[pair+":duplicate"]+=1;continue
                seen.add(digest)
                rank=int(digest,16)
                row=dict(pair=pair,source_id=a,target_id=b,original=at,translation=bt,
                    source_contexts_sha256=receipt["sha256"],source_tokens=left,target_tokens=right)
                item=(-rank,digest,row)
                heap=heaps[pair]
                if len(heap)<args.maximum:heapq.heappush(heap,item)
                elif item[:2]>heap[0][:2]:heapq.heapreplace(heap,item)
        print(json.dumps(dict(source=str(path),counts=dict(counts))),flush=True)
    outputs=[]
    for pair,heap in heaps.items():
        assert heap
        text=args.output/(pair+".txt");provenance=args.output/(pair+"-provenance.jsonl")
        with text.open("x") as lines,provenance.open("x") as rows:
            for _,_,row in sorted(heap,reverse=True):
                lines.write(" ".join(t[0].casefold() for t in row["source_tokens"])+" ||| "+
                    " ".join(t[0].casefold() for t in row["target_tokens"])+"\n")
                rows.write(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n")
        outputs.append(dict(pair=pair,rows=len(heap),text_sha256=sha_file(text),
            provenance_sha256=sha_file(provenance),bytes=text.stat().st_size+provenance.stat().st_size))
    receipt=dict(complete=True,compiler_sha256=sha_file(Path(__file__)),
        sources=sources,evaluation_exclusions=evidence,counts=dict(counts),outputs=outputs,
        policy="Hash-ranked bounded direct development pairs with published lexical anchors; explicit evaluation text excluded.",
        scope="Authoring experiment. Statistical alignments are not accepted vocabulary mappings.",
        independent_semantic_acceptance=False,runtime_integrated=False)
    write_json(args.output/"receipt.json",receipt);print(json.dumps(dict(outputs=outputs)),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--contexts",type=Path,action="append",required=True)
    p.add_argument("--evaluation-exclusions",type=Path,action="append",required=True)
    p.add_argument("--evaluation-cases",type=Path,action="append",required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--maximum",type=int,default=100000)
    build(p.parse_args())
