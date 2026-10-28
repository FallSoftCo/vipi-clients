#!/usr/bin/env python3
"""Apply the modern-sense eligibility correction without rereading all lexicons."""
import argparse,hashlib,json,shutil,sqlite3,time
from pathlib import Path
from build_wiktextract import PARTS,EXCLUDED
from build_lexical_shards import canonical,digest_file

POLICY="native-linked-modern-lexemes-6"
def build(a):
    before=json.loads(a.base.read_text())
    inventory=json.loads((a.inventory.parent/"receipt.json").read_text())
    assert before["inventory_sha256"]==inventory["sha256"] and inventory["complete_source_scan"]
    # The retained inventory is immutable and already pinned by its source
    # receipt. Read only raw entry tags, not bulk lexical evidence again.
    source=sqlite3.connect(a.inventory.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    source.execute("PRAGMA cache_size=-8192")
    compiler=digest_file(Path(__file__))
    release=hashlib.sha256(canonical(dict(base_release=before["release_id"],
        source_inventory=inventory["sha256"],compiler=compiler,policy=POLICY)).encode()).hexdigest()
    a.output.mkdir(parents=True,exist_ok=False)
    shards=[];updates=[]
    for row in before["shards"]:
        started=time.monotonic();original=a.base.parent/(row["language"]+".sqlite")
        assert digest_file(original)==row["sha256"] and original.stat().st_size==row["bytes"]
        path=a.output/original.name;shutil.copyfile(original,path)
        with sqlite3.connect(path) as db:
            db.execute("PRAGMA temp_store=FILE");db.execute("PRAGMA cache_size=-8192")
            candidates=db.execute("SELECT id,headword,pos,senses FROM lexemes WHERE target_safe=0 AND senses>0 ORDER BY id").fetchall()
            candidates=[r for r in candidates if r[2] in PARTS]
            changed=[]
            for offset in range(0,len(candidates),200):
                batch=candidates[offset:offset+200];ids=[r[0] for r in batch]
                marks=",".join("?" for _ in ids)
                entries={i:(lang,head,pos,set(json.loads(tags))) for i,lang,head,pos,tags in source.execute(
                    "SELECT source_line,language,headword,part_of_speech,tags FROM native_entries WHERE source_line IN ("+marks+") ORDER BY source_line",ids)}
                assert len(entries)==len(batch)
                for identifier,head,pos,senses in batch:
                    lang,native_head,native_pos,tags=entries[identifier]
                    assert lang==row["language"] and head==native_head and pos==native_pos
                    if not tags&EXCLUDED:
                        db.execute("UPDATE lexemes SET target_safe=1 WHERE id=? AND target_safe=0",(identifier,))
                        changed.append(dict(id=identifier,headword=head,pos=pos,modern_senses=senses))
            fields=dict(policy=POLICY,release_id=release,base_release_id=before["release_id"],
                eligibility_delta_compiler_sha256=compiler,
                eligibility_delta_policy="retain-modern-senses-with-mixed-alternative-entry-1")
            for k,v in fields.items():db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)",(k,canonical(v)))
            db.commit()
            db.execute("ATTACH DATABASE ? AS base",(original.resolve().as_uri()+"?mode=ro&immutable=1",))
            assert not db.execute("""SELECT 1 FROM lexemes n JOIN base.lexemes o USING(id)
                WHERE n.headword<>o.headword OR n.normalized<>o.normalized OR n.pos<>o.pos
                OR n.source_safe<>o.source_safe OR n.senses<>o.senses OR n.source_url<>o.source_url
                OR n.target_safe<o.target_safe LIMIT 1""").fetchone()
            assert db.execute("SELECT count(*) FROM lexemes").fetchone()[0]==row["counts"]["lexemes"]
            assert db.execute("PRAGMA quick_check").fetchone()[0]=="ok"
        update=dict(language=row["language"],newly_eligible=len(changed),entries=changed)
        updates.append(update)
        result=dict(row,sha256=digest_file(path),bytes=path.stat().st_size,seconds=round(time.monotonic()-started,3))
        result["counts"]=dict(row["counts"],newly_eligible_lexemes=len(changed))
        shards.append(result)
        print(canonical(dict(language=row["language"],newly_eligible=len(changed),seconds=result["seconds"])),flush=True)
        (a.output/"progress.json").write_text(json.dumps(dict(complete=False,shards=shards,updates=updates),ensure_ascii=False,indent=2)+"\n")
    source.close()
    summary=dict(before,policy=POLICY,release_id=release,base_release_id=before["release_id"],shards=shards,
        compiler_sha256=compiler,base_compiler_sha256=before["compiler_sha256"],
        total_bytes=sum(s["bytes"] for s in shards),runtime_qualified=False,release_ready=False,
        mutation_scope="Existing lexemes.target_safe may change 0 to 1; metadata records the delta. All other lexical rows, surfaces and source eligibility remain unchanged.")
    (a.output/"catalog.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    (a.output/"eligibility-changes.json").write_text(json.dumps(dict(complete=True,languages=updates),ensure_ascii=False,indent=2)+"\n")
    shutil.copy2(a.base.parent/"ATTRIBUTION.txt",a.output/"ATTRIBUTION.txt")
    with (a.output/"ATTRIBUTION.txt").open("a") as f:f.write("\nChange: preserve ordinary lexical meanings when the same entry also records an alternative/form-of sense. Original definitions and readings retained.\n")
    (a.output/"progress.json").unlink()
    print(canonical(dict(complete=True,release_id=release,total_bytes=summary["total_bytes"],newly_eligible=sum(x["newly_eligible"] for x in updates))))
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for n in ["base","inventory","output"]:p.add_argument("--"+n,type=Path,required=True)
    build(p.parse_args())
