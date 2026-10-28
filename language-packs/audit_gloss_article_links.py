#!/usr/bin/env python3
"""Measure existing bilingual links falsely rejected by noun definition articles.
This audit does not alter packs, create new translations, or claim accuracy.
"""
import argparse,hashlib,importlib.util,json,sqlite3,time
from pathlib import Path
from native_lemma_links import NativeLinks
from context_hints import has_scope,qualifier

def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def main(a):
    receipt=json.loads((a.inventory.parent/"receipt.json").read_text())
    catalog=json.loads(a.catalog.read_text())
    assert receipt["sha256"]==catalog["inventory_sha256"]
    spec=importlib.util.spec_from_file_location("historical_native_links",a.previous_linker)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    a.output.mkdir(parents=True,exist_ok=False)
    source=sqlite3.connect(a.inventory.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    source.execute("PRAGMA cache_size=-32768")
    results=[];counts={};started=time.monotonic()
    try:
        for shard in catalog["shards"]:
            language=shard["language"]
            if language=="en":continue
            path=a.catalog.parent/(language+".sqlite")
            assert sha(path)==shard["sha256"]
            db=sqlite3.connect(path.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
            before=old.NativeLinks(source,language,{})
            after=NativeLinks(source,language,{})
            counts[language]=dict(scanned_lexemes=0,article_lexemes=0,restorable_terms=0)
            try:
                candidates=db.execute("""SELECT DISTINCT l.id,l.headword FROM lexemes l JOIN terms t ON t.lexeme=l.id
                    WHERE l.pos='noun' AND t.eligible=0 ORDER BY l.id""")
                for identifier,headword in candidates:
                    counts[language]["scanned_lexemes"]+=1
                    pre=before.simple_glosses(identifier);post=after.simple_glosses(identifier)
                    added=post-pre
                    if not added:continue
                    counts[language]["article_lexemes"]+=1
                    terms=list(db.execute("SELECT sense,reading,eligible,qualifiers FROM terms WHERE lexeme=?",(identifier,)))
                    scoped={sense for sense,reading,eligible,q in terms if has_scope(q)}
                    for sense,reading,eligible,q in terms:
                        if eligible or qualifier(q) or sense in scoped:continue
                        english=source.execute("SELECT source_word FROM senses WHERE id=?",(sense,)).fetchone()
                        if english and english[0].lower() in added:
                            results.append(dict(language=language,native_line=identifier,headword=headword,
                                sense=sense,english=english[0],reading=reading,qualifiers=q,
                                before_glosses=sorted(pre),after_glosses=sorted(post)))
                            counts[language]["restorable_terms"]+=1
            finally:
                db.close();before.close();after.close()
            print(json.dumps(dict(language=language,**counts[language])),flush=True)
    finally:source.close()
    (a.output/"links.json").write_text(json.dumps(results,ensure_ascii=False,indent=2)+"\n")
    report=dict(complete=True,dictionary_release=catalog["release_id"],inventory_sha256=receipt["sha256"],
        previous_linker_sha256=sha(a.previous_linker),compiler_sha256=sha(Path(__file__)),
        counts=counts,links=len(results),lexemes=len({(x["language"],x["native_line"]) for x in results}),
        semantic_accuracy_claim=False,mutated_pack=False,elapsed_seconds=round(time.monotonic()-started,2))
    (a.output/"receipt.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ["inventory","catalog","previous-linker","output"]:p.add_argument("--"+name,type=Path,required=True)
    main(p.parse_args())
