#!/usr/bin/env python3
"""Hash existing source sentences so new corpora cannot duplicate evaluation data.

All existing partitions are excluded, also preventing double-counted development
evidence. This artifact contains hashes only, never sentence text or translations.
"""
import argparse
import bz2
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from conversation_corpus import key,sha_file,write_json


def fingerprint(language,text):
    return hashlib.sha256((language+"\0"+key(text)).encode()).digest()


def build(args):
    args.output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic()
    corpus_receipt=json.loads((args.corpus.parent/"receipt.json").read_text())
    sw_receipt=json.loads((args.swahili/"receipt.json").read_text())
    sw_path=args.swahili/"swh_sentences_detailed.tsv.bz2"
    assert sha_file(args.corpus)==corpus_receipt["sha256"]
    assert sha_file(sw_path)==sw_receipt["sha256"]
    path=args.output/"hashes.sqlite"
    output=sqlite3.connect(path)
    output.executescript("""PRAGMA temp_store=FILE;PRAGMA cache_size=-32768;
        CREATE TABLE hashes(digest BLOB PRIMARY KEY CHECK(length(digest)=32)) WITHOUT ROWID;
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;""")
    counts=Counter();batch=[]
    def add(language,text):
        counts[language]+=1;batch.append((fingerprint(language,text),))
        if len(batch)>=5000:
            output.executemany("INSERT OR IGNORE INTO hashes VALUES (?)",batch);output.commit();batch.clear()
    with sqlite3.connect(args.corpus.resolve().as_uri()+"?mode=ro&immutable=1",uri=True) as source:
        for language,normalized in source.execute("SELECT language,normalized FROM sentences NOT INDEXED"):
            add(language,normalized)
    with bz2.open(sw_path,"rt",encoding="utf-8") as stream:
        for line in stream:
            fields=line.rstrip("\n").split("\t")
            assert len(fields)>=3 and fields[1]=="swh"
            add("sw",fields[2])
    output.executemany("INSERT OR IGNORE INTO hashes VALUES (?)",batch);output.commit()
    receipt=dict(schema="vipi-existing-corpus-exclusions-1",source_corpus_sha256=corpus_receipt["sha256"],
        source_corpus_receipt_sha256=sha_file(args.corpus.parent/"receipt.json"),
        swahili_source_sha256=sw_receipt["sha256"],compiler_sha256=sha_file(Path(__file__)),
        normalization_source_sha256=sha_file(Path(__file__).with_name("conversation_corpus.py")),
        policy="exclude every existing development and reserved sentence; propagate matches through new direct-link components",
        normalization="language + NUL + NFC/casefold/collapsed-whitespace; punctuation preserved",
        source_rows=dict(counts),hashes=output.execute("SELECT count(*) FROM hashes").fetchone()[0],
        contains_sentence_text=False,complete=True)
    output.execute("INSERT INTO metadata VALUES ('receipt',?)",(json.dumps(receipt,sort_keys=True),));output.commit()
    assert output.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    output.close()
    receipt.update(bytes=path.stat().st_size,sha256=sha_file(path),seconds=round(time.monotonic()-started,3))
    write_json(args.output/"receipt.json",receipt)
    print(json.dumps(receipt,sort_keys=True))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ["corpus","swahili","output"]:parser.add_argument("--"+field,type=Path,required=True)
    build(parser.parse_args())
