#!/usr/bin/env python3
"""Apply only audited exact native-definition corroborations to existing links."""
import argparse,hashlib,json,shutil,sqlite3,time
from collections import defaultdict
from contextlib import closing
from pathlib import Path
from build_wiktextract import canonical,digest_file
POLICY = "native-linked-exact-sense-gloss-9"
from native_lemma_links import NativeLinks
from context_hints import has_scope,qualifier

def build(a):
    assert POLICY=="native-linked-exact-sense-gloss-9"
    base=json.loads(a.base.read_text())
    proof=json.loads((a.links.parent/"receipt.json").read_text())
    inventory=json.loads((a.inventory.parent/"receipt.json").read_text())
    assert proof["complete"] and not proof["mutated_pack"]
    assert proof["dictionary_release"]==base["release_id"]
    assert proof["source_catalog_sha256"]==digest_file(a.base)
    assert proof["verified_links_sha256"]==digest_file(a.links)
    assert base["inventory_sha256"]==inventory["sha256"]==proof["source_inventory_sha256"]
    changes=json.loads(a.links.read_text())
    assert len(changes)==proof["verified_existing_links"]
    by_language=defaultdict(list)
    for row in changes:by_language[row["language"]].append(row)
    assert set(by_language)<={row["language"] for row in base["shards"]}
    identity=dict(base_release=base["release_id"],proof_sha256=digest_file(a.links.parent/"receipt.json"),
        links_sha256=digest_file(a.links),compiler_sha256=digest_file(Path(__file__)),
        linker_sha256=digest_file(Path(__file__).with_name("native_lemma_links.py")),
        gloss_parser_sha256=digest_file(Path(__file__).with_name("build_native_gloss_links.py")),policy=POLICY)
    release=hashlib.sha256(canonical(identity).encode()).hexdigest()
    a.output.mkdir(parents=True,exist_ok=False)
    shards=[];delta=[]
    with closing(sqlite3.connect(a.inventory.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)) as source:
        source.execute("PRAGMA cache_size=-16384")
        for row in base["shards"]:
            language=row["language"];original=a.base.parent/(language+".sqlite")
            assert digest_file(original)==row["sha256"] and original.stat().st_size==row["bytes"]
            output=a.output/original.name;shutil.copyfile(original,output)
            links=NativeLinks(source,language,{})
            expected=set()
            try:
                with closing(sqlite3.connect(output)) as db:
                    db.execute("PRAGMA temp_store=FILE");db.execute("PRAGMA cache_size=-16384")
                    for item in by_language.get(language,[]):
                        identifier,sense,reading,q=(item[k] for k in ["native_line","sense","reading","qualifiers"])
                        actual=db.execute("""SELECT l.headword,s.label,t.eligible FROM terms t
                            JOIN lexemes l ON l.id=t.lexeme JOIN senses s ON s.id=t.sense
                            WHERE t.lexeme=? AND t.sense=? AND t.reading=? AND t.qualifiers=?""",(identifier,sense,reading,q)).fetchone()
                        assert actual==(item["headword"],item["label"],0),item
                        assert links.entry(identifier)[1]==item["headword"]
                        assert links.matching_sense_gloss(identifier,item["label"])
                        english=source.execute("SELECT source_word FROM senses WHERE id=?",(sense,)).fetchone()
                        assert english and english[0]==item["english_word"]
                        assert links.simple_glosses(identifier) and english[0].lower() not in links.simple_glosses(identifier)
                        assert not qualifier(q)
                        assert not any(has_scope(v) for (v,) in db.execute("SELECT qualifiers FROM terms WHERE lexeme=? AND sense=?",(identifier,sense)))
                        key=(identifier,sense,reading,q);assert key not in expected;expected.add(key)
                        assert db.execute("UPDATE terms SET eligible=1 WHERE lexeme=? AND sense=? AND reading=? AND qualifiers=? AND eligible=0",key).rowcount==1
                    for k,v in dict(policy=POLICY,release_id=release,base_release_id=base["release_id"],
                        exact_sense_gloss_delta=identity,exact_sense_gloss_terms=len(expected)).items():
                        db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)",(k,canonical(v)))
                    db.commit()
                    db.execute("ATTACH DATABASE ? AS old",(original.resolve().as_uri()+"?mode=ro&immutable=1",))
                    assert db.execute("SELECT count(*) FROM terms").fetchone()==db.execute("SELECT count(*) FROM old.terms").fetchone()
                    actual=set(db.execute("""SELECT n.lexeme,n.sense,n.reading,n.qualifiers FROM terms n JOIN old.terms o USING(lexeme,sense,reading,qualifiers)
                        WHERE n.eligible<>o.eligible AND n.eligible=1 AND o.eligible=0"""))
                    assert actual==expected
                    assert not db.execute("""SELECT 1 FROM terms n JOIN old.terms o USING(lexeme,sense,reading,qualifiers)
                        WHERE n.eligible<o.eligible LIMIT 1""").fetchone()
                    assert db.execute("PRAGMA quick_check").fetchone()[0]=="ok"
            finally:links.close()
            result=dict(row,sha256=digest_file(output),bytes=output.stat().st_size,
                recompiled=False,exact_sense_gloss_terms=len(expected),compiler_counts_inherited_from_base=True)
            shards.append(result);delta.append(dict(language=language,changed_terms=len(expected)))
            print(canonical(delta[-1]),flush=True)
    catalog=dict(base,policy=POLICY,release_id=release,base_release_id=base["release_id"],shards=shards,
        changed_languages=sorted(by_language),compiler_sha256=identity["compiler_sha256"],
        linker_sha256=identity["linker_sha256"],base_compiler_sha256=base["compiler_sha256"],delta_identity=identity,
        total_bytes=sum(r["bytes"] for r in shards),runtime_qualified=False,release_ready=False,
        mutation_scope="Only individually revalidated existing terms.eligible change 0 to 1; metadata records the bounded correction. Fresh affected-pair contexts required.")
    for name,value in [("catalog.json",catalog),("eligibility-changes.json",dict(complete=True,languages=delta,links=changes))]:
        (a.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")
    (a.output/"ATTRIBUTION.txt").write_text((a.base.parent/"ATTRIBUTION.txt").read_text()+
        "\nChange: exact complete native definitions corroborate matching published translation sense labels. Other meanings and usage restrictions retained.\n")
    print(canonical(dict(complete=True,release_id=release,changed_terms=sum(x["changed_terms"] for x in delta))))
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ["base","inventory","links","output"]:p.add_argument("--"+name,type=Path,required=True)
    build(p.parse_args())
