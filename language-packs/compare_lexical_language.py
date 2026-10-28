#!/usr/bin/env python3
"""Compare complete dictionary records and usable links for one language."""
import argparse,hashlib,json,sqlite3
from contextlib import closing
from pathlib import Path
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def build(a):
    before=json.loads(a.before.read_text());after=json.loads(a.after.read_text())
    old=next(r for r in before["shards"] if r["language"]==a.language)
    new=next(r for r in after["shards"] if r["language"]==a.language)
    paths=[a.before.parent/(a.language+".sqlite"),a.after.parent/(a.language+".sqlite")]
    for path,row in zip(paths,[old,new]):
        assert path.stat().st_size==row["bytes"] and sha(path)==row["sha256"]
    with closing(sqlite3.connect(paths[1].as_uri()+"?mode=ro&immutable=1",uri=True)) as db:
        db.execute("PRAGMA temp_store=FILE")
        db.execute("ATTACH DATABASE ? AS previous",(paths[0].as_uri()+"?mode=ro&immutable=1",))
        counts={}
        for table in ["lexemes","senses","terms","surfaces","guards","lemma_links","carrier_evidence"]:
            counts[table]=dict(
                before=db.execute("SELECT count(*) FROM previous."+table).fetchone()[0],
                after=db.execute("SELECT count(*) FROM "+table).fetchone()[0],
                added=db.execute("SELECT count(*) FROM (SELECT * FROM "+table+" EXCEPT SELECT * FROM previous."+table+")").fetchone()[0],
                removed=db.execute("SELECT count(*) FROM (SELECT * FROM previous."+table+" EXCEPT SELECT * FROM "+table+")").fetchone()[0])
        def links(prefix):
            return {tuple(row[:3]):dict(identifier=row[0],sense=row[1],reading=row[2],headword=row[3],
                    pos=row[4],label=row[5],lexeme_url=row[6],sense_url=row[7])
                for row in db.execute("SELECT t.lexeme,t.sense,t.reading,l.headword,l.pos,s.label,l.source_url,s.source_url FROM "+
                    prefix+"terms t JOIN "+prefix+"lexemes l ON l.id=t.lexeme JOIN "+prefix+"senses s ON s.id=t.sense WHERE t.eligible=1 AND l.target_safe=1")}
        left,right=links("previous."),links("")
        added=[right[k] for k in sorted(right.keys()-left.keys())]
        removed=[left[k] for k in sorted(left.keys()-right.keys())]
        safety=[dict(identifier=i,headword=h,source_before=sb,source_after=sa,target_before=tb,target_after=ta)
            for i,h,sb,sa,tb,ta in db.execute("""SELECT n.id,n.headword,o.source_safe,n.source_safe,o.target_safe,n.target_safe
                FROM lexemes n JOIN previous.lexemes o USING(id)
                WHERE n.source_safe<>o.source_safe OR n.target_safe<>o.target_safe ORDER BY n.headword,n.id""")]
    result=dict(complete=True,language=a.language,before_release=before["release_id"],after_release=after["release_id"],
        before_sha256=old["sha256"],after_sha256=new["sha256"],tables=counts,
        usable_links_added=added,usable_links_removed=removed,existing_safety_changes=safety,
        native_qualified=False,semantic_accuracy_claim=False,compiler_sha256=sha(Path(__file__)))
    assert not a.output.exists();a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(dict(tables=counts,usable_links_added=len(added),usable_links_removed=len(removed),
        existing_safety_changes=len(safety))))
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ["before","after","output"]:p.add_argument("--"+name,type=lambda s:Path(s).resolve(),required=True)
    p.add_argument("--language",required=True);build(p.parse_args())
