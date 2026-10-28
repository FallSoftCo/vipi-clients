#!/usr/bin/env python3
"""Select complete attested noun spellings for an experimental context pass.

Selection is dictionary eligibility, not proof of the noun's contextual POS.
Every existing aligned counterpart of each selected spelling must be retained.
"""
import argparse,json,sqlite3,time
from collections import Counter
from contextlib import closing
from pathlib import Path
from build_wiktextract import canonical,digest_file

def build(args):
    started=time.monotonic();catalog=json.loads(args.dictionary.read_text())
    args.output.mkdir(parents=True,exist_ok=False)
    path=args.output/"source-words.sqlite";counts=Counter()
    with closing(sqlite3.connect(path)) as output:
        output.execute("CREATE TABLE source_words(language TEXT,word TEXT,PRIMARY KEY(language,word)) WITHOUT ROWID")
        for row in catalog["shards"]:
            language=row["language"]
            if language not in args.languages:continue
            source=args.dictionary.parent/(language+".sqlite")
            assert digest_file(source)==row["sha256"]
            with closing(sqlite3.connect(source.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)) as db:
                db.create_function("utf16length",1,lambda v:len(v.encode("utf-16-le"))//2,deterministic=True)
                rows=db.execute("""SELECT DISTINCT f.normalized FROM surfaces f JOIN lexemes l ON l.id=f.lexeme
                    WHERE l.pos='noun' AND l.target_safe=1 AND f.mode IN (1,2)
                    AND f.start=0 AND f.end=utf16length(f.surface)
                    AND EXISTS(SELECT 1 FROM terms t JOIN senses s ON s.id=t.sense
                        WHERE t.lexeme=l.id AND t.eligible=1 AND s.explicit=1)""")
                output.executemany("INSERT INTO source_words VALUES (?,?)",((language,r[0]) for r in rows))
                counts[language]=output.execute("SELECT count(*) FROM source_words WHERE language=?",(language,)).fetchone()[0]
        assert set(counts)==set(args.languages) and all(counts.values())
        output.commit();assert output.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    receipt=dict(schema="vipi-source-word-filter-1",policy="complete-explicit-noun-spellings-1",
        complete=True,source_release_id=catalog["release_id"],dictionary_catalog_sha256=digest_file(args.dictionary),
        compiler_sha256=digest_file(Path(__file__)),sha256=digest_file(path),bytes=path.stat().st_size,
        counts=dict(counts),languages=sorted(counts),semantic_accuracy_claim=False,
        selection_uses_evaluation_text=False,seconds=round(time.monotonic()-started,2))
    (args.output/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(canonical(receipt),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ["dictionary","output"]:p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--languages",nargs="+",required=True)
    build(p.parse_args())
