#!/usr/bin/env python3
"""Tiny synthetic native fixture: selected pair, corrupt stream, oversized output."""
from pathlib import Path
import hashlib,json,sqlite3,sys,tempfile,zlib
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"language-packs"))
from build_lexical_shards import SCHEMA
out=ROOT/"qa/immersion/installer-fixture-assets/lexical-fixture"
out.mkdir(parents=True,exist_ok=False)
release="d"*64;files=[]
def pack(id,data,expected=None):
    path=out/(id+".sqlite.zlib");path.write_bytes(zlib.compress(data,6))
    row=dict(id=id,file=path.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
        compressed_bytes=path.stat().st_size,compressed_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    if expected:row.update(expected)
    files.append(row)
with tempfile.TemporaryDirectory(dir=out) as temp:
    for lang,word in [("en","apple"),("es","manzana")]:
        path=Path(temp)/(lang+".sqlite")
        with sqlite3.connect(path) as db:
            db.executescript(SCHEMA)
            meta=dict(schema="vipi-lexical-shard-2",policy="native-linked-noun-carriers-5",language=lang,
                source_inventory_sha256="a"*64,release_id=release)
            db.executemany("INSERT INTO metadata VALUES (?,?)",[(k,json.dumps(v)) for k,v in meta.items()])
            db.execute("INSERT INTO lexemes VALUES (1,?,?,?,1,1,1,?)",(word,word,"noun","https://example.invalid/synthetic"))
            db.execute("INSERT INTO senses VALUES ('fruit-apple','apple fruit','noun',1,'https://example.invalid/synthetic')")
            db.execute("INSERT INTO terms VALUES (1,'fruit-apple','',1,'{}')")
            db.execute("INSERT INTO surfaces VALUES (?,1,?,0,?,0,1,'[]')",(word,word,len(word)))
        pack("d-"+lang,path.read_bytes())
    path=Path(temp)/"witness.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript("""CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE witnesses(source TEXT,target TEXT,word TEXT,counterpart TEXT,cue TEXT,support INTEGER,total INTEGER);""")
        meta=dict(schema="vipi-context-witnesses-1",policy="experimental-direct-reference-agreement-1",
            source_release_id=release,minimum_support=3,minimum_agreement=.98,pairs={"en-es":0,"es-en":0})
        db.executemany("INSERT INTO metadata VALUES (?,?)",[(k,json.dumps(v)) for k,v in meta.items()])
    pack("w-en-es",path.read_bytes())
    pack("d-fr",b"corrupt stream contents"*100,dict(bytes=4096,sha256="0"*64))
    pack("w-en-fr",path.read_bytes())
    pack("d-de",(Path(temp)/"en.sqlite").read_bytes(),dict(bytes=512))
    pack("w-de-en",path.read_bytes())
    pack("d-pt",(Path(temp)/"en.sqlite").read_bytes())
(out/"catalog.json").write_text(json.dumps(dict(schema="vipi-bundled-lexical-1",dictionary_release=release,files=files),indent=2)+"\n")
(out/"NOTICE.txt").write_text("Synthetic installer fixtures only. Not linguistic evidence or app data.\n")
print(json.dumps(dict(files=len(files),total_bytes=sum(p.stat().st_size for p in out.iterdir()))))
