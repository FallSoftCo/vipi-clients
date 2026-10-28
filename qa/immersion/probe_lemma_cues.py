#!/usr/bin/env python3
"""Development-only probe: aggregate context cues by attested dictionary head.

No runtime pack is emitted. All original observations (including competing
targets) are transformed before applying the existing agreement threshold.
"""
import argparse,hashlib,json,sqlite3,time
from collections import Counter
from contextlib import closing
from pathlib import Path
from functools import lru_cache
PARTS={'noun','verb','adj','adjective','adv','adverb'}
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def ro(path):
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    db.execute('PRAGMA temp_store=FILE');db.execute('PRAGMA cache_size=-16384')
    return db
def build(args):
    started=time.monotonic()
    receipt=json.loads((args.observations.parent/'receipt.json').read_text())
    catalog=json.loads(args.dictionary.read_text())
    assert receipt['complete'] and receipt['observations_sha256']==sha(args.observations)
    assert receipt['source_release_id']==catalog['release_id']
    assert receipt['disjoint_source_proof']['same_dictionary_catalog_sha256']==sha(args.dictionary)
    args.output.mkdir(exist_ok=False,parents=True)
    shards={}
    try:
        for row in catalog['shards']:
            path=args.dictionary.parent/(row['language']+'.sqlite')
            assert sha(path)==row['sha256']
            shards[row['language']]=ro(path)
        @lru_cache(maxsize=200000)
        def lemma(language,word):
            db=shards[language]
            rows=db.execute("""SELECT DISTINCT l.normalized,l.pos,l.target_safe
                FROM surfaces s JOIN lexemes l ON l.id=s.lexeme WHERE s.normalized=?""",(word,)).fetchall()
            if not rows or any(pos not in PARTS or safe!=1 for _,pos,safe in rows):return None
            heads={head for head,_,_ in rows}
            if len(heads)!=1:return None
            head=heads.pop()
            if not head or len(head)>96 or not any(c.isalpha() for c in head):return None
            guard=db.execute("SELECT target_blocked,reason FROM guards WHERE normalized=?",(word,)).fetchone()
            if guard and (guard[0] or guard[1]=='name'):return None
            return head
        counts=Counter()
        output=args.output/'lemma-observations.sqlite'
        with closing(ro(args.observations)) as source,closing(sqlite3.connect(output)) as db:
            db.executescript("""PRAGMA temp_store=FILE;PRAGMA cache_size=-32768;
                CREATE TABLE pairs(id INTEGER PRIMARY KEY,source TEXT,target TEXT);
                CREATE TABLE atoms(id INTEGER PRIMARY KEY,value TEXT UNIQUE);
                CREATE TABLE observations(pair INTEGER,word INTEGER,cue INTEGER,target INTEGER,
                    sentence INTEGER,counterpart INTEGER,PRIMARY KEY(pair,word,cue,target,sentence)) WITHOUT ROWID;""")
            pairs={i:(a,b) for i,a,b in source.execute('SELECT * FROM pairs')}
            db.executemany('INSERT INTO pairs VALUES (?,?,?)',[(i,*p) for i,p in pairs.items()])
            atoms=dict(source.execute('SELECT id,value FROM atoms'))
            db.executemany('INSERT INTO atoms VALUES (?,?)',atoms.items())
            ids={value:i for i,value in atoms.items()}
            def atom(value):
                if value not in ids:
                    ids[value]=len(ids)+1;db.execute('INSERT INTO atoms VALUES (?,?)',(ids[value],value))
                return ids[value]
            mapped={}
            for source_language,cue in source.execute("""SELECT DISTINCT p.source,o.cue
                FROM observations o JOIN pairs p ON p.id=o.pair"""):
                raw=atoms[cue]
                if not raw.startswith(('L:','R:')):continue
                root=lemma(source_language,raw[2:])
                if root:
                    mapped[(source_language,cue)]=atom(raw[:2]+'@lemma:'+root)
                    counts['mapped_cue_forms']+=1
                    if root!=raw[2:]:counts['inflected_cue_forms']+=1
            db.commit();batch=[]
            for pair,word,cue,target,sentence,counterpart in source.execute('SELECT * FROM observations'):
                counts['input_observations']+=1
                alias=mapped.get((pairs[pair][0],cue))
                if alias is None:continue
                batch.append((pair,word,alias,target,sentence,counterpart))
                if len(batch)>=20000:
                    db.executemany('INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?,?)',batch);db.commit();batch=[]
            db.executemany('INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?,?)',batch);db.commit()
            counts['deduplicated_lemma_observations']=db.execute('SELECT count(*) FROM observations').fetchone()[0]
            db.executescript("""CREATE TABLE frequencies AS SELECT pair,word,cue,target,count(*) support FROM observations GROUP BY pair,word,cue,target;
                CREATE TABLE totals AS SELECT pair,word,cue,sum(support) total FROM frequencies GROUP BY pair,word,cue;
                CREATE UNIQUE INDEX totals_lookup ON totals(pair,word,cue);
                CREATE TABLE witnesses AS SELECT p.source,p.target,w.value word,t.value counterpart,c.value cue,f.support,z.total
                  FROM frequencies f JOIN totals z USING(pair,word,cue)
                  JOIN pairs p ON p.id=f.pair JOIN atoms w ON w.id=f.word
                  JOIN atoms t ON t.id=f.target JOIN atoms c ON c.id=f.cue
                  WHERE f.support>=3 AND f.support*1.0/z.total>=0.98;
                CREATE UNIQUE INDEX witness_lookup ON witnesses(source,target,word,counterpart,cue);""")
            counts['witnesses']=db.execute('SELECT count(*) FROM witnesses').fetchone()[0]
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            examples=db.execute("""SELECT * FROM witnesses WHERE source='en' AND target='ar'
                AND word IN ('books','children','friends','questions','keys') ORDER BY word,cue""").fetchall()
        value=dict(complete=True,development_probe_only=True,runtime_integrated=False,semantic_accuracy_claim=False,
            policy='Unique supplied head across all indexed lexical analyses; grammar, names, unknown or conflicting heads withheld.',
            source_observations_sha256=receipt['observations_sha256'],dictionary_catalog_sha256=sha(args.dictionary),
            compiler_sha256=sha(Path(__file__)),output_sha256=sha(output),bytes=output.stat().st_size,
            minimum_support=3,minimum_agreement=.98,counts=counts,seconds=round(time.monotonic()-started,2))
        (args.output/'receipt.json').write_text(json.dumps(value,indent=2)+'\n')
        (args.output/'examples.json').write_text(json.dumps(examples,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(value),flush=True)
    finally:
        for db in shards.values():db.close()
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['observations','dictionary','output']:parser.add_argument('--'+name,type=Path,required=True)
    build(parser.parse_args())
