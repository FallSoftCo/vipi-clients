#!/usr/bin/env python3
"""Bind unchanged written-word witnesses to a strictly checked morphology extension.

This cannot approve new dictionary links or change agreement/quality thresholds.
Original mining provenance remains explicit; every new artifact has a new hash.
"""
import argparse
import json
from pathlib import Path
import shutil
import sqlite3
from build_wiktextract import canonical,digest_file


def readonly(path):
    return sqlite3.connect(path.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)


def prove(old_path,new_path):
    with readonly(new_path) as db:
        db.execute("ATTACH DATABASE ? AS prior",(old_path.resolve().as_uri()+"?mode=ro&immutable=1",))
        evidence={}
        for table in ["senses","terms","lexemes","surfaces"]:
            assert not db.execute(f"SELECT * FROM prior.{table} EXCEPT SELECT * FROM main.{table} LIMIT 1").fetchall(), table+" changed existing evidence"
            added=db.execute(f"SELECT count(*) FROM (SELECT * FROM main.{table} EXCEPT SELECT * FROM prior.{table})").fetchone()[0]
            if table in ["senses","terms"]:
                assert added==0, "New translation/sense evidence requires a fresh context build"
            evidence[table+"_added"]=added
        before=dict(db.execute("SELECT key,value FROM prior.metadata"))
        after=dict(db.execute("SELECT key,value FROM main.metadata"))
        for key in ["source_inventory_sha256","source_sha256","redirects_sha256","native_gloss_links_sha256","linker_sha256","language"]:
            assert before[key]==after[key], "Changed source identity: "+key
        assert json.loads(after["policy"])=="native-linked-noun-carriers-5"
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    return evidence


def main(args):
    baseline=json.loads((args.baseline/"catalog.json").read_text())
    updated=json.loads((args.shards/"catalog.json").read_text())
    parent=json.loads((args.witnesses.parent/"receipt.json").read_text())
    assert baseline["inventory_sha256"]==updated["inventory_sha256"]
    old={s["language"]:s for s in baseline["shards"]}
    new={s["language"]:s for s in updated["shards"]}
    assert old.keys()==new.keys() and not updated["release_ready"]
    assert parent["sha256"]==digest_file(args.witnesses)
    with readonly(args.witnesses) as db:
        metadata={k:json.loads(v) for k,v in db.execute("SELECT key,value FROM metadata")}
    assert metadata["schema"]=="vipi-context-witnesses-1" and not metadata["release_ready"]
    assert metadata["source_release_id"]==baseline["release_id"]
    proofs={}
    for language in sorted(old):
        before=args.baseline/(language+".sqlite");after=args.shards/(language+".sqlite")
        assert digest_file(before)==old[language]["sha256"] and digest_file(after)==new[language]["sha256"]
        proofs[language]=prove(before,after)
    args.output.mkdir(parents=True,exist_ok=False)
    target=args.output/"witnesses.sqlite"
    assert not Path(str(args.witnesses)+"-wal").exists()
    shutil.copyfile(args.witnesses,target)
    metadata.update(source_release_id=updated["release_id"],
        context_compilation_release_id=baseline["release_id"],
        release_adapter_sha256=digest_file(Path(__file__)),parent_witness_sha256=parent["sha256"],
        adapted_catalog_sha256=digest_file(args.shards/"catalog.json"),
        base_catalog_sha256=digest_file(args.baseline/"catalog.json"),
        adaptation_policy="unchanged-dictionary-links-added-carriers-1",adaptation_proof=proofs)
    with sqlite3.connect(target) as db:
        db.executemany("INSERT OR REPLACE INTO metadata VALUES (?,?)",[(k,canonical(v)) for k,v in metadata.items()])
        db.commit()
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        assert db.execute("SELECT count(*) FROM witnesses").fetchone()[0]==metadata["counts"]["witnesses"]
    result=dict(metadata,bytes=target.stat().st_size,sha256=digest_file(target),complete=True)
    (args.output/"receipt.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    (args.output/"ATTRIBUTION.txt").write_text((args.witnesses.parent/"ATTRIBUTION.txt").read_text()+
        "\nRelease binding adapted after verifying unchanged dictionary senses/links and retained lexical evidence.\n")
    print(canonical(dict(bytes=result["bytes"],sha256=result["sha256"],source_release_id=updated["release_id"],proofs=proofs)))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ["baseline","shards","witnesses","output"]:parser.add_argument("--"+field,type=Path,required=True)
    main(parser.parse_args())
