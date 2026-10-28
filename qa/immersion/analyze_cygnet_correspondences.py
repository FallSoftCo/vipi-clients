#!/usr/bin/env python3
"""Diagnostic independent concept corroboration; never authorize substitutions."""
import argparse,hashlib,json,sqlite3,time,unicodedata
from collections import defaultdict,Counter
from contextlib import closing
from pathlib import Path
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def key(v):return unicodedata.normalize("NFC",v).lower()
def main():
    parser=argparse.ArgumentParser()
    for name in ("source","gaps","output"):parser.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args();started=time.monotonic()
    pin=json.loads((args.source/"receipt.json").read_text())
    for asset in pin["assets"]:
        f=args.source/asset["database"]
        assert f.stat().st_size==asset["uncompressed_bytes"] and sha(f)==asset["database_sha256"]
    cases=json.loads(args.gaps.read_text())
    wanted=defaultdict(set)
    for row in cases:
        case=row["case"]
        assert case["source"] in ("en","es") and case["target"] in ("en","es")
        for link in row["unqualified_dictionary_links"]:
            wanted[case["source"]].add(key(link["source"]));wanted[case["target"]].add(key(link["target"]))
    concepts=defaultdict(set);pos=defaultdict(set);counts=Counter();results=[]
    # Keep every observed concept/POS for a written form, including ambiguity.
    # The upstream accent-stripping key is never used as equality evidence.
    with closing(sqlite3.connect((args.source/"cygnet.db").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)) as db:
        db.execute("PRAGMA trusted_schema=OFF")
        for lang,form,category,concept in db.execute("""SELECT l.code,f.form,e.pos,s.synset_rowid
            FROM forms f JOIN entries e ON e.rowid=f.entry_rowid
            JOIN languages l ON l.rowid=e.language_rowid JOIN senses s ON s.entry_rowid=e.rowid
            WHERE l.code IN ('en','es')"""):
            written=key(form)
            if written not in wanted[lang]:continue
            concepts[(lang,written)].add(concept);pos[(lang,written)].add(category)
        for row in cases:
            case=row["case"];offered={}
            for link in row["unqualified_dictionary_links"]:
                if link["source_hard_grammar"]:continue
                source=(case["source"],key(link["source"]));target=(case["target"],key(link["target"]))
                left=concepts[source];right=concepts[target]
                if not left or not left<=right:continue
                token=tuple(link[k] for k in ("source","target","start","end","target_start","target_end"))
                offered[token]=dict(span={k:link[k] for k in ("source","target","start","end","target_start","target_end")},
                    source_concepts=sorted(left),target_concepts=sorted(right),source_pos=sorted(pos[source]),target_pos=sorted(pos[target]))
            if offered:
                results.append(dict(case=case,already_selected=row["selected"],unqualified_corroborated_pairs=list(offered.values())))
                counts["messages_with_corroborated_pairs"]+=1
                counts["previously_empty_messages"]+=not row["selected"]
                counts["corroborated_pairs"]+=len(offered)
        resources=[dict(zip(("code","version","language","license","url"),r)) for r in db.execute("""
            SELECT r.code,r.version,l.code,r.licence,r.url FROM resources r
            LEFT JOIN languages l ON l.rowid=r.language_rowid WHERE l.code IN ('en','es') OR r.code='cili'""")]
    args.output.mkdir(exist_ok=False,parents=True)
    f=args.output/"candidates.json";f.write_text(json.dumps(results,ensure_ascii=False,indent=2)+chr(10))
    receipt=dict(complete=True,counts=dict(counts),gaps_sha256=sha(args.gaps),source_receipt_sha256=sha(args.source/"receipt.json"),
        compiler_sha256=sha(Path(__file__)),candidates_sha256=sha(f),seconds=round(time.monotonic()-started,2),resources=resources,
        runtime_integrated=False,production_promoted=False,semantic_accuracy_claim=False,redistribution_qualified=False,
        limitations=["All known Cygnet concepts are preserved; neither dictionary is assumed complete.",
            "Shared spellings do not merge Cygnet concepts with Wiktionary sense IDs.",
            "No POS, inflection, sentence, idiom, reading, case or overlap acceptance is implied.",
            "Dictionary corroboration is only a diagnostic lead; no per-row license or contextual acceptance yet.",
            "This observed development sample cannot establish population or per-language coverage."])
    (args.output/"receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+chr(10))
    print(json.dumps(dict(complete=True,counts=dict(counts),seconds=receipt["seconds"])),flush=True)
if __name__=="__main__":main()
