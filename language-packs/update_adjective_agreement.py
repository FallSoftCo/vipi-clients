#!/usr/bin/env python3
"""Enable only already supplied, bounded adjective agreement forms."""
import argparse,hashlib,json,shutil,sqlite3
from contextlib import closing
from pathlib import Path
from adjective_agreement import whole_form
from build_wiktextract import canonical,digest_file

POLICY="native-linked-adjective-agreement-10"
def build(a):
    base=json.loads(a.base.read_text())
    assert base["policy"]=="native-linked-exact-sense-gloss-9"
    recipe=dict(base_release=base["release_id"],base_catalog_sha256=digest_file(a.base),
        compiler_sha256=digest_file(Path(__file__)),
        adjective_agreement_sha256=digest_file(Path(__file__).with_name("adjective_agreement.py")),
        full_compiler_sha256=digest_file(Path(__file__).with_name("build_lexical_shards.py")),policy=POLICY)
    release=hashlib.sha256(canonical(recipe).encode()).hexdigest()
    a.output.mkdir(exist_ok=False)
    shards=[];changes=[]
    with (a.output/"changed-surfaces.jsonl").open("x") as evidence:
        for row in base["shards"]:
            language=row["language"];original=a.base.parent/(language+".sqlite")
            assert original.stat().st_size==row["bytes"] and digest_file(original)==row["sha256"]
            target=a.output/original.name;shutil.copyfile(original,target)
            changed=0;lexemes=set();forms=set()
            with closing(sqlite3.connect(target)) as db:
                db.execute("PRAGMA temp_store=FILE");db.execute("PRAGMA cache_size=-16384")
                count=db.execute("SELECT count(*) FROM surfaces").fetchone()[0]
                rows=db.execute("""SELECT s.normalized,s.lexeme,s.surface,s.start,s.end,s.number,s.mode,s.features,l.headword,l.pos
                    FROM surfaces s JOIN lexemes l ON l.id=s.lexeme WHERE s.mode=0 AND l.target_safe=1 AND l.pos='adj'""").fetchall()
                for *surface,head,pos in rows:
                    normalized,lexeme,written,start,end,number,mode,features=surface
                    rule=whole_form(head,written,pos,json.loads(features),language)
                    if not rule:continue
                    new_start,new_end,new_number,new_mode=rule
                    cursor=db.execute("""UPDATE surfaces SET start=?,end=?,number=?,mode=?
                        WHERE normalized=? AND lexeme=? AND surface=? AND start=? AND end=? AND number=? AND mode=? AND features=?""",
                        (*rule,*surface))
                    assert cursor.rowcount==1
                    actual=db.execute("""SELECT start,end,number,mode FROM surfaces
                        WHERE normalized=? AND lexeme=? AND surface=? AND features=? AND mode=2""",
                        (normalized,lexeme,written,features)).fetchall()
                    assert tuple(rule) in actual
                    evidence.write(json.dumps(dict(language=language,headword=head,old=surface,
                        new=[normalized,lexeme,written,*rule,features]),ensure_ascii=False,separators=(",",":"))+"\n")
                    changed+=1;lexemes.add(lexeme);forms.add(written)
                for key,value in dict(policy=POLICY,release_id=release,base_release_id=base["release_id"],
                    adjective_agreement_delta=recipe,adjective_agreement_surfaces=changed).items():
                    db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)",(key,canonical(value)))
                db.commit()
                assert db.execute("SELECT count(*) FROM surfaces").fetchone()[0]==count
                assert db.execute("PRAGMA quick_check").fetchone()[0]=="ok"
            result=dict(row,sha256=digest_file(target),bytes=target.stat().st_size,
                recompiled=False,adjective_agreement_surfaces=changed,compiler_counts_inherited_from_base=True)
            shards.append(result)
            changes.append(dict(language=language,changed_surfaces=changed,lexemes=len(lexemes),written_forms=len(forms)))
            print(canonical(changes[-1]),flush=True)
    catalog=dict(base,policy=POLICY,release_id=release,base_release_id=base["release_id"],
        compiler_sha256=recipe["compiler_sha256"],delta_identity=recipe,
        changed_languages=[r["language"] for r in changes if r["changed_surfaces"]],shards=shards,
        changed_surfaces_sha256=digest_file(a.output/"changed-surfaces.jsonl"),
        total_bytes=sum(r["bytes"] for r in shards),runtime_qualified=False,release_ready=False,
        mutation_scope="Only existing unselected adjective agreement surfaces become complete-word forms; no words, senses, readings, source/target safety flags or target terms changed. Fresh contexts required.")
    for name,value in [("catalog.json",catalog),("surface-changes.json",dict(complete=True,languages=changes))]:
        (a.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")
    (a.output/"ATTRIBUTION.txt").write_text((a.base.parent/"ATTRIBUTION.txt").read_text()+
        "\nChange: existing published Romance adjective gender/number forms are selectable as complete lexical words. Degree and other features remain restricted.\n")
    print(canonical(dict(complete=True,release_id=release,total_changed_surfaces=sum(r["changed_surfaces"] for r in changes))))

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ["base","output"]:p.add_argument("--"+name,type=Path,required=True)
    build(p.parse_args())
