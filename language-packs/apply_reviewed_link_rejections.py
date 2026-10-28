#!/usr/bin/env python3
"""Apply exact reviewed negative meaning links without merging native entries."""
import argparse,hashlib,json,shutil,sqlite3
from contextlib import closing
from pathlib import Path
from build_wiktextract import canonical,digest_file
import lexical_link_reviews
RULE="reviewed-native-entry-link-rejection-1"
def readonly(path):
    return sqlite3.connect(path.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
def build(args):
    base=json.loads(args.base.read_text())
    assert base["inventory_sha256"]==lexical_link_reviews.INVENTORY_SHA256==digest_file(args.inventory)
    row=next(r for r in base["shards"] if r["language"]==args.language)
    source=args.base.parent/(args.language+".sqlite")
    assert digest_file(source)==row["sha256"] and source.stat().st_size==row["bytes"]
    selected={k:v for k,v in lexical_link_reviews.REJECTIONS.items() if k[0]==args.language}
    assert selected
    recipe=dict(rule=RULE,language=args.language,base_catalog_sha256=digest_file(args.base),
        source_inventory_sha256=base["inventory_sha256"],reviews_sha256=digest_file(Path(lexical_link_reviews.__file__)),
        compiler_sha256=digest_file(Path(__file__)))
    release=hashlib.sha256(canonical(recipe).encode()).hexdigest()
    args.output.mkdir(parents=True,exist_ok=False)
    target=args.output/source.name;shutil.copyfile(source,target);changes=[]
    with closing(readonly(args.inventory)) as inventory,closing(sqlite3.connect(target)) as db:
        db.execute("PRAGMA temp_store=FILE");db.execute("PRAGMA cache_size=-8192")
        for (language,identifier,sense),review in sorted(selected.items()):
            entry=inventory.execute("SELECT language,headword,source_url FROM native_entries WHERE source_line=?",(identifier,)).fetchone()
            assert entry==(language,review["headword"],review["native_url"])
            definitions=[json.loads(g)[-1] for (g,) in inventory.execute(
                "SELECT glosses FROM native_senses WHERE source_line=? ORDER BY sense_index",(identifier,))]
            assert definitions==review["native_definitions"],"Reviewed native definitions changed"
            label,url=db.execute("SELECT label,source_url FROM senses WHERE id=?",(sense,)).fetchone()
            assert label==review["label"] and url==review["sense_url"]
            count=db.execute("SELECT count(*) FROM terms WHERE lexeme=? AND sense=? AND eligible=1",(identifier,sense)).fetchone()[0]
            assert count>0,"This revision is not a fresh negative-link correction"
            db.execute("UPDATE terms SET eligible=0 WHERE lexeme=? AND sense=? AND eligible=1",(identifier,sense))
            changes.append(dict(lexeme=identifier,headword=review["headword"],sense=sense,rows=count))
        metadata={k:json.loads(v) for k,v in db.execute("SELECT key,value FROM metadata")}
        assert metadata["release_id"]==base["release_id"] and metadata["language"]==args.language
        for key,value in dict(release_id=release,reviewed_link_recipe=recipe).items():
            db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)",(key,canonical(value)))
        db.commit()
        db.execute("ATTACH DATABASE ? AS prior",(source.resolve().as_uri()+"?mode=ro&immutable=1",))
        # Preserve every source analysis, guard, spelling, reading and sense.
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            if table in {"metadata","terms"}:continue
            assert table.replace("_","").isalnum()
            for a,b in [("main","prior"),("prior","main")]:
                assert not db.execute(f"SELECT 1 FROM (SELECT * FROM {a}.{table} EXCEPT SELECT * FROM {b}.{table}) LIMIT 1").fetchone(),table
        fields="lexeme,sense,reading,qualifiers"
        for a,b in [("main","prior"),("prior","main")]:
            assert not db.execute(f"SELECT 1 FROM (SELECT {fields} FROM {a}.terms EXCEPT SELECT {fields} FROM {b}.terms) LIMIT 1").fetchone()
        differences=db.execute("""SELECT n.lexeme,n.sense,n.eligible,o.eligible
            FROM terms n JOIN prior.terms o USING(lexeme,sense,reading,qualifiers)
            WHERE n.eligible<>o.eligible""").fetchall()
        assert len(differences)==sum(r["rows"] for r in changes)
        assert all((args.language,lexeme,sense) in selected and new==0 and old==1 for lexeme,sense,new,old in differences)
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    result=dict(row,sha256=digest_file(target),bytes=target.stat().st_size,
        counts=dict(row["counts"],reviewed_negative_links=len(differences)))
    catalog=dict(schema=base["schema"],policy=metadata["policy"],release_id=release,
        inventory_sha256=base["inventory_sha256"],shards=[result],total_bytes=result["bytes"],recipe=recipe,
        runtime_qualified=False,release_ready=False)
    (args.output/"catalog.json").write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+"\n")
    receipt=dict(complete=True,recipe=recipe,catalog_sha256=digest_file(args.output/"catalog.json"),changes=changes,
        unchanged_native_records=True,only_eligible_one_to_zero=True,positive_links_added=0,
        native_qualified=False,accepted_for_context_mining=True,independent_semantic_acceptance=False)
    (args.output/"receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n")
    (args.output/"ATTRIBUTION.txt").write_text((args.base.parent/"ATTRIBUTION.txt").read_text()+
        "\nExact author-reviewed negative links, preserving distinct native meanings and all supplied forms/readings.\n")
    print(json.dumps(dict(complete=True,changed_links=len(differences),bytes=result["bytes"],
        catalog_sha256=receipt["catalog_sha256"]),ensure_ascii=False),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ["base","inventory","output"]:p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--language",required=True)
    build(p.parse_args())
