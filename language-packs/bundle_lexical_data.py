#!/usr/bin/env python3
"""Build app-signed compressed public dictionaries and exact pair contexts.

A context evidence release may be reused only after proving its full lexical
relations still exist unchanged. Added eligibility is recorded as a migration,
not as new corpus evidence or an accuracy certification.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import zlib

def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()
def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def metadata(db):
    return {k:json.loads(v) for k,v in db.execute("SELECT key,value FROM metadata")}
def compatible(base,candidate,base_root,candidate_root,output):
    assert base["inventory_sha256"]==candidate["inventory_sha256"]
    assert {s["language"] for s in base["shards"]}=={s["language"] for s in candidate["shards"]}
    rows=[]
    for after in candidate["shards"]:
        before=next(s for s in base["shards"] if s["language"]==after["language"])
        old=base_root/(after["language"]+".sqlite")
        new=candidate_root/old.name
        assert sha(old)==before["sha256"] and sha(new)==after["sha256"]
        with closing(sqlite3.connect(new.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)) as db:
            db.execute("PRAGMA temp_store=FILE")
            db.execute("PRAGMA cache_size=-8192")
            db.execute("ATTACH DATABASE ? AS previous",(old.resolve().as_uri()+"?mode=ro&immutable=1",))
            unchanged=["terms","senses","lemma_links"]
            for table in unchanged:
                assert not db.execute(f"SELECT * FROM {table} EXCEPT SELECT * FROM previous.{table} LIMIT 1").fetchone(),table
                assert not db.execute(f"SELECT * FROM previous.{table} EXCEPT SELECT * FROM {table} LIMIT 1").fetchone(),table
            # New noun carriers may add surfaces and competitors. Existing
            # lexical data and source/target protection cannot be weakened.
            for table in ["surfaces","carrier_evidence"]:
                assert not db.execute(f"SELECT * FROM previous.{table} EXCEPT SELECT * FROM {table} LIMIT 1").fetchone(),table
            assert not db.execute("""SELECT 1 FROM previous.guards o LEFT JOIN guards n USING(normalized)
                WHERE n.normalized IS NULL OR n.blocked<o.blocked OR n.target_blocked<o.target_blocked
                OR n.protect_inner<o.protect_inner OR n.reason<>o.reason LIMIT 1""").fetchone()
            stable="id,headword,normalized,pos,source_safe,senses,source_url"
            assert not db.execute(f"SELECT {stable} FROM previous.lexemes EXCEPT SELECT {stable} FROM lexemes LIMIT 1").fetchone()
            assert not db.execute("""SELECT 1 FROM previous.lexemes o JOIN lexemes n USING(id)
                WHERE n.target_safe<o.target_safe LIMIT 1""").fetchone()
            changed=db.execute("""SELECT count(*) FROM previous.lexemes o JOIN lexemes n USING(id)
                WHERE n.target_safe>o.target_safe""").fetchone()[0]
            rows.append(dict(language=after["language"],before_sha256=before["sha256"],after_sha256=after["sha256"],
                newly_eligible_lexemes=changed,existing_relations_preserved=True))
    proof=dict(schema="vipi-lexical-compatibility-1",base_release=base["release_id"],
        candidate_release=candidate["release_id"],complete=True,languages=rows,
        scope="Existing sense/term/lemma relations equal; existing surfaces and carrier evidence preserved; guards and source eligibility not weakened; target eligibility only added.",
        semantic_accuracy_claim=False)
    output.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+"\n")
    return proof

def compress(source,output,id):
    destination=output/(id+".sqlite.zlib")
    compressor=zlib.compressobj(6)
    uncompressed=0
    with source.open("rb") as input,destination.open("xb") as out:
        while chunk:=input.read(1024*1024):
            uncompressed+=len(chunk);out.write(compressor.compress(chunk))
        out.write(compressor.flush())
    # Verify the shipped stream and exact expanded digest with bounded memory.
    digest=hashlib.sha256();decoder=zlib.decompressobj();count=0
    with destination.open("rb") as f:
        while chunk:=f.read(65_536):
            data=decoder.decompress(chunk)
            count+=len(data);digest.update(data)
        data=decoder.flush();count+=len(data);digest.update(data)
    assert decoder.eof and not decoder.unused_data and count==uncompressed
    actual=sha(source);assert digest.hexdigest()==actual
    return dict(id=id,file=destination.name,bytes=uncompressed,sha256=actual,
        compressed_bytes=destination.stat().st_size,compressed_sha256=sha(destination))

def build(a):
    base=json.loads(a.base.read_text());catalog=json.loads(a.catalog.read_text())
    contexts=json.loads(a.contexts.read_text())
    assert contexts["complete"] and contexts["exact_row_equality_verified"]
    assert contexts["dictionary_release"]==base["release_id"]
    a.output.mkdir(parents=True,exist_ok=False)
    proof=compatible(base,catalog,a.base.parent,a.catalog.parent,a.output/"compatibility.json")
    records=[]
    for row in catalog["shards"]:
        path=a.catalog.parent/(row["language"]+".sqlite")
        assert path.stat().st_size==row["bytes"] and sha(path)==row["sha256"]
        records.append(compress(path,a.output,"d-"+row["language"]))
        print(canonical(dict(stage="dictionary",language=row["language"],compressed=records[-1]["compressed_bytes"])),flush=True)
    for row in contexts["pair_packs"]:
        source=a.contexts.parent/row["file"];assert sha(source)==row["sha256"]
        temp=a.output/("prepare-context-"+row["pair"]+".sqlite")
        shutil.copyfile(source,temp)
        try:
            with closing(sqlite3.connect(temp)) as db:
                meta=metadata(db);assert meta["source_release_id"]==base["release_id"]
                changes=dict(source_release_id=catalog["release_id"],
                    context_evidence_dictionary_release_id=meta.get("context_evidence_dictionary_release_id",base["release_id"]),
                    dictionary_compatibility_sha256=sha(a.output/"compatibility.json"),
                    original_pair_database_sha256=row["sha256"])
                for k,v in changes.items():
                    db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)",(k,canonical(v)))
                db.commit()
                db.execute("ATTACH DATABASE ? AS original",(source.resolve().as_uri()+"?mode=ro&immutable=1",))
                assert not db.execute("SELECT * FROM witnesses EXCEPT SELECT * FROM original.witnesses LIMIT 1").fetchone()
                assert not db.execute("SELECT * FROM original.witnesses EXCEPT SELECT * FROM witnesses LIMIT 1").fetchone()
                assert db.execute("PRAGMA quick_check").fetchone()[0]=="ok"
            records.append(compress(temp,a.output,"w-"+row["pair"]))
        finally:temp.unlink(missing_ok=True)
    manifest=dict(schema="vipi-bundled-lexical-1",dictionary_release=catalog["release_id"],
        context_evidence_dictionary_release=base["release_id"],compatibility_sha256=sha(a.output/"compatibility.json"),
        files=records,compressed_bytes=sum(r["compressed_bytes"] for r in records),
        all_expanded_bytes=sum(r["bytes"] for r in records),languages=[r["language"] for r in catalog["shards"]],
        directed_pairs=contexts["directed_pairs"],compiler_sha256=sha(Path(__file__)),
        semantic_accuracy_claim=False,store_ready=False)
    for file in (a.catalog.parent/"ATTRIBUTION.txt",a.contexts.parent/"ATTRIBUTION.txt"):
        with (a.output/"ATTRIBUTION.txt").open("a") as f:f.write(file.read_text()+"\n")
    (a.output/"catalog.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    print(canonical({k:v for k,v in manifest.items() if k!="files"}))
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ["base","catalog","contexts","output"]:p.add_argument("--"+name,type=Path,required=True)
    build(p.parse_args())
