#!/usr/bin/env python3
"""Add supplied Arabic plural carriers with their exact lexical-focus readings.

Only previously unusable, already indexed normalized forms are extended.
This preserves every competing native analysis gathered by the baseline build.
Case-marked forms, duals, construct states and ambiguous readings stay out.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import unicodedata

from build_wiktextract import EXCLUDED, canonical, digest_file
from context_hints import lookup_key

RULE = "supplied-arabic-plural-reading-1"
POLICY = "native-linked-arabic-plural-readings-16"
READING_SCHEMA = """
CREATE TABLE surface_readings(normalized TEXT NOT NULL,lexeme INTEGER NOT NULL,
 sense TEXT NOT NULL,reading TEXT NOT NULL,source_indices TEXT NOT NULL,
 PRIMARY KEY(normalized,lexeme,sense,reading)) WITHOUT ROWID;
"""
BAD = EXCLUDED | {"dual","singular","construct","nominative","accusative","genitive","error-unrecognized-form"}

def candidates(rows):
    bare = defaultdict(list)
    definite = []
    for index,written,reading,raw_tags in rows:
        tags = set(json.loads(raw_tags))
        if "plural" not in tags or tags & BAD or not reading or len(reading)>96:
            continue
        if any(c in reading for c in "/,;()") or not all(
            "LATIN" in unicodedata.name(c,"") or c in " -’'ʿʾ" or unicodedata.combining(c)
            for c in reading):
            continue
        plain = lookup_key(written,"ar")
        if len(plain)<2 or not all("\u0620"<=c<="\u064a" for c in plain):
            continue
        if "definite" in tags:
            if plain.startswith("ال"):
                definite.append((plain,index,written,reading,tags))
        elif not plain.startswith("ال"):
            bare[plain].append((index,written,reading,tags))
    for plain, variants in sorted(bare.items()):
        readings = {r[2] for r in variants}
        if len(readings) != 1:
            continue
        reading = readings.pop()
        indices = sorted({r[0] for r in variants})
        yield dict(written=plain,focus_start=0,focus_end=len(plain),reading=reading,
            indices=indices,features=[RULE,"plural"],evidence=dict(
                supplied_forms=[dict(index=i,form=w,reading=r,tags=sorted(t)) for i,w,r,t in variants],
                normalization="NFC/lower/Arabic harakat removal as in the pinned inventory"))
        for carrier,index,written,full_reading,tags in definite:
            if carrier[2:] != plain:
                continue
            yield dict(written=carrier,focus_start=2,focus_end=len(carrier),reading=reading,
                indices=sorted({*indices,index}),features=[RULE,"plural","definite"],
                evidence=dict(supplied_definite=dict(index=index,form=written,reading=full_reading,tags=sorted(tags)),
                    lexical_reading_forms=[dict(index=i,form=w,reading=r,tags=sorted(t)) for i,w,r,t in variants],
                    normalization="Supplied definite plural; exact article remains outside the lexical focus."))


def reading_key(value):
    # Equivalent published hamza/ayn notation only; never infer vowels.
    return unicodedata.normalize("NFC",value).replace("ʔ","ʾ").replace("'","ʾ").replace("’","ʾ").replace("ʻ","ʿ")

def head_readings(rows,head):
    result=set()
    for index,written,reading,raw_tags in rows:
        tags=set(json.loads(raw_tags))
        if "singular" in tags and not tags & ((BAD-{"singular"})|{"plural","definite"}) and lookup_key(written,"ar")==lookup_key(head,"ar") and reading:
            result.add(reading_key(reading))
    return result

def build(args):
    baseline=json.loads(args.base.read_text())
    row=next(r for r in baseline["shards"] if r["language"]=="ar")
    source=args.base.parent/"ar.sqlite"
    assert digest_file(source)==row["sha256"] and source.stat().st_size==row["bytes"]
    supplied=json.loads(args.readings.with_name("receipt.json").read_text())
    assert supplied["complete"] and supplied["inventory_sha256"]==baseline["inventory_sha256"]
    assert supplied["sha256"]==digest_file(args.readings)
    recipe=dict(policy=POLICY,rule=RULE,base_catalog_sha256=digest_file(args.base),
        base_shard_sha256=row["sha256"],readings_sha256=supplied["sha256"],
        compiler_sha256=digest_file(Path(__file__)))
    release=hashlib.sha256(canonical(recipe).encode()).hexdigest()
    args.output.mkdir(parents=True,exist_ok=False)
    output=args.output/"ar.sqlite";shutil.copyfile(source,output)
    counts=Counter();examples=[]
    with closing(sqlite3.connect(args.readings.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)) as evidence, closing(sqlite3.connect(output)) as db:
        db.execute("PRAGMA temp_store=FILE")
        db.execute("PRAGMA cache_size=-16384")
        db.executescript(READING_SCHEMA)
        lexemes=db.execute("SELECT id,headword FROM lexemes WHERE pos='noun' AND target_safe=1 AND EXISTS (SELECT 1 FROM terms WHERE lexeme=id AND eligible=1)").fetchall()
        for lexeme,head in lexemes:
            raw=evidence.execute("SELECT form_index,form,reading,tags FROM form_readings WHERE source_line=? ORDER BY form_index",(lexeme,)).fetchall()
            heads=head_readings(raw,head)
            if len(heads)!=1:
                counts["missing_or_ambiguous_head_reading"]+=1;continue
            linked=sorted({sense for sense,reading in db.execute(
                "SELECT sense,reading FROM terms WHERE lexeme=? AND eligible=1",(lexeme,))
                if reading_key(reading) in heads})
            if not linked:
                counts["no_pronunciation_matched_meaning"]+=1;continue
            grouped={}
            for candidate in candidates(raw):
                key=candidate["written"]
                old=grouped.get(key)
                if old is None:grouped[key]=candidate
                else:
                    assert old["reading"]==candidate["reading"] and old["focus_start"]==candidate["focus_start"]
                    old["indices"]=sorted(set(old["indices"])|set(candidate["indices"]))
            for word,candidate in sorted(grouped.items()):
                # Existing mode-0 forms already caused the baseline compiler
                # to gather all same-spelling competitors and word guards.
                modes={r[0] for r in db.execute("SELECT mode FROM surfaces WHERE lexeme=? AND normalized=?",(lexeme,word))}
                if not modes:counts["not_previously_indexed"]+=1;continue
                if modes & {1,2,3}:counts["existing_usable_geometry"]+=1;continue
                db.execute("INSERT INTO surfaces VALUES (?,?,?,?,?,?,?,?)",(word,lexeme,word,
                    candidate["focus_start"],candidate["focus_end"],2,3,canonical(candidate["features"])))
                for sense in linked:
                    db.execute("INSERT INTO surface_readings VALUES (?,?,?,?,?)",(word,lexeme,sense,candidate["reading"],canonical(candidate["indices"])))
                candidate["evidence"]["head_readings"]=sorted(heads)
                candidate["evidence"]["allowed_senses"]=linked
                db.execute("INSERT INTO carrier_evidence VALUES (?,?,?,?)",(lexeme,word,RULE,canonical(candidate["evidence"])))
                counts["new_plural_carriers"]+=1
                counts["definite" if candidate["focus_start"] else "bare"]+=1
                if len(examples)<30 or head in {"كتاب","صديق","مدينة","طالب","طفل"}:
                    examples.append(dict(lexeme=lexeme,head=head,**candidate))
        assert counts["new_plural_carriers"]>0
        for key,value in dict(policy=POLICY,release_id=release,surface_reading_schema="vipi-surface-reading-2",
            surface_reading_rule=RULE,source_form_readings_sha256=supplied["sha256"],plural_reading_recipe=recipe).items():
            db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)",(key,canonical(value)))
        db.commit()
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        assert db.execute("PRAGMA foreign_key_check").fetchone() is None
        shard_counts=dict(row["counts"])
        for table in ["surfaces","carrier_evidence"]:
            shard_counts[table]=db.execute("SELECT count(*) FROM "+table).fetchone()[0]
        shard_counts["indexed_written_forms"]=db.execute("SELECT count(DISTINCT normalized) FROM surfaces WHERE mode IN (1,2,3)").fetchone()[0]
        shard_counts["indexed_carriers"]=db.execute("SELECT count(DISTINCT normalized) FROM surfaces WHERE mode=3").fetchone()[0]
        shard_counts[RULE]=counts["new_plural_carriers"]
    shard=dict(language="ar",bytes=output.stat().st_size,sha256=digest_file(output),counts=shard_counts)
    catalog=dict(schema=baseline["schema"],policy=POLICY,release_id=release,inventory_sha256=baseline["inventory_sha256"],
        shards=[shard],total_bytes=shard["bytes"],compiler_sha256=recipe["compiler_sha256"],recipe=recipe,
        release_ready=False,runtime_qualified=False,limits=[
        "Only supplied case-neutral plural nouns with unambiguous lexical readings.",
        "All source meanings and competing native analyses remain. Each new plural only links meanings with its source entry headword pronunciation; context is still required.",
        "Exact unmarked carriers only; new readings never fall back to the singular headword reading."])
    (args.output/"catalog.json").write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+"\n")
    (args.output/"examples.json").write_text(json.dumps(examples,ensure_ascii=False,indent=2)+"\n")
    receipt=dict(complete=True,catalog_sha256=digest_file(args.output/"catalog.json"),recipe=recipe,counts=counts,
        native_qualified=False,accepted_for_context_mining=False,semantic_accuracy_claim=False)
    (args.output/"receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n")
    (args.output/"ATTRIBUTION.txt").write_text((args.base.parent/"ATTRIBUTION.txt").read_text()+"\n"+
        (args.readings.parent/"ATTRIBUTION.txt").read_text()+"\n"+
        "Extension: exact supplied Arabic plural forms/readings; article remains outside lexical focus.\n")
    print(canonical(receipt),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("base","readings","output"):p.add_argument("--"+name,type=Path,required=True)
    build(p.parse_args())
