#!/usr/bin/env python3
"""Add complete, attested present forms. Mode 5 needs contextual native matching."""
import argparse,hashlib,json,shutil,sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path
from build_wiktextract import canonical,digest_file
from context_hints import lookup_key
from present_verb_forms import variants,RULE,POLICY,SCHEMA,LANGUAGES

def build(args):
    base=json.loads(args.base.read_text())
    assert digest_file(args.inventory)==base["inventory_sha256"]
    languages=sorted(args.language or LANGUAGES)
    assert set(languages)<=LANGUAGES
    recipe=dict(policy=POLICY,compiler_sha256=digest_file(Path(__file__)),
        grammar_sha256=digest_file(Path(__file__).with_name("present_verb_forms.py")),
        base_catalog_sha256=digest_file(args.base),inventory_sha256=base["inventory_sha256"],
        languages=languages,english_head_reference="https://dictionary.cambridge.org/grammar/british-grammar/present-simple-i-work")
    release=hashlib.sha256(canonical(recipe).encode()).hexdigest()
    args.output.mkdir(parents=True,exist_ok=False);shards=[];totals={};examples=[]
    with closing(sqlite3.connect(args.inventory.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)) as inventory:
        for language in languages:
            row=next(r for r in base["shards"] if r["language"]==language)
            source=args.base.parent/(language+".sqlite")
            assert digest_file(source)==row["sha256"]
            target=args.output/source.name;shutil.copyfile(source,target);counts=Counter()
            with closing(sqlite3.connect(target)) as db:
                db.execute("PRAGMA temp_store=FILE");db.execute("PRAGMA cache_size=-16384")
                entries=db.execute("""SELECT id,headword FROM lexemes WHERE pos='verb' AND target_safe=1
                    AND EXISTS (SELECT 1 FROM terms WHERE lexeme=id AND eligible=1)""").fetchall()
                for lexeme,head in entries:
                    raw=inventory.execute("SELECT form,tags FROM native_forms WHERE source_line=? ORDER BY form,tags",(lexeme,)).fetchall()
                    for form in variants(head,raw,language):
                        word=lookup_key(form["written"],language)
                        if not db.execute("SELECT 1 FROM surfaces WHERE normalized=? AND lexeme=?",(word,lexeme)).fetchone():
                            counts["not_previously_indexed"]+=1;continue
                        end=len(form["written"].encode("utf-16-le"))//2
                        db.execute("INSERT INTO surfaces VALUES (?,?,?,?,?,?,?,?)",
                            (word,lexeme,form["written"],0,end,0,5,canonical(form["features"])))
                        db.execute("INSERT INTO carrier_evidence VALUES (?,?,?,?)",
                            (lexeme,form["written"],RULE,canonical(dict(source_line=lexeme,headword=head,**form))))
                        counts["complete_present_forms"]+=1
                        if head in {"work","cook","play","drink","read","trabajar","cocinar","jugar","beber","leer","travailler","arbeiten","trabalhar"}:
                            examples.append(dict(language=language,lexeme=lexeme,headword=head,**form))
                for k,v in dict(policy=POLICY,release_id=release,present_verb_schema=SCHEMA,present_verb_rule=RULE,present_verb_recipe=recipe).items():
                    db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)",(k,canonical(v)))
                db.commit()
                db.execute("ATTACH DATABASE ? AS prior",(source.resolve().as_uri()+"?mode=ro&immutable=1",))
                tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name<>'metadata'")]
                for table in tables:
                    assert not db.execute(f"SELECT * FROM prior.{table} EXCEPT SELECT * FROM main.{table} LIMIT 1").fetchone(),table
                    if table not in {"surfaces","carrier_evidence"}:
                        assert not db.execute(f"SELECT * FROM main.{table} EXCEPT SELECT * FROM prior.{table} LIMIT 1").fetchone(),table
                assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
                counts.update(dict(preserved_native_tables=True))
                shard_counts=dict(row["counts"])
                for table in ["surfaces","carrier_evidence"]:shard_counts[table]=db.execute("SELECT count(*) FROM "+table).fetchone()[0]
                shard_counts[RULE]=counts["complete_present_forms"]
            shards.append(dict(language=language,bytes=target.stat().st_size,sha256=digest_file(target),counts=shard_counts))
            totals[language]=dict(counts);print(canonical(dict(language=language,counts=counts)),flush=True)
    catalog=dict(schema=base["schema"],policy=POLICY,release_id=release,inventory_sha256=base["inventory_sha256"],
        shards=shards,total_bytes=sum(r["bytes"] for r in shards),recipe=recipe,release_ready=False,runtime_qualified=False,
        limits=["Whole present verbs require context, finite-clause evidence, and compatible person/number on both sides.",
            "Past-syncretic forms are withheld. All original analyses, meanings and guards remain.",
            "Italian stress-marked forms are not normalized or included. No new translations or spellings generated."])
    (args.output/"catalog.json").write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+"\n")
    (args.output/"examples.json").write_text(json.dumps(examples,ensure_ascii=False,indent=2)+"\n")
    (args.output/"receipt.json").write_text(json.dumps(dict(complete=True,counts=totals,recipe=recipe,
        catalog_sha256=digest_file(args.output/"catalog.json"),native_qualified=False,semantic_accuracy_claim=False),indent=2)+"\n")
    (args.output/"ATTRIBUTION.txt").write_text((args.base.parent/"ATTRIBUTION.txt").read_text()+
        "\nComplete supplied present verb forms; English head classification reference retained in recipe. No generated forms.\n")
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ["base","inventory","output"]:p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--language",action="append",choices=sorted(LANGUAGES))
    build(p.parse_args())
