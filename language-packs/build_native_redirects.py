#!/usr/bin/env python3
"""Preserve explicit native entry redirects from the pinned upstream dump."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sqlite3
import time
from build_wiktextract import canonical,clean,digest_file,form_ok,MAX_LINE,LANGUAGES

def build(source,output):
    pin=json.loads(Path(__file__).with_name('sources').joinpath('wiktextract-20261021.json').read_text())
    assert source.stat().st_size==pin['source_bytes'] and digest_file(source)==pin['source_sha256']
    output.mkdir(parents=True,exist_ok=False);path=output/'redirects.sqlite';counts=Counter();start=time.monotonic();line=0
    with sqlite3.connect(path) as db:
        db.executescript('''PRAGMA temp_store=FILE;
            CREATE TABLE redirects(source_line INTEGER NOT NULL,language TEXT NOT NULL,headword TEXT NOT NULL,
            target TEXT NOT NULL,PRIMARY KEY(source_line,target)) WITHOUT ROWID;
            CREATE TABLE rejected(source_line INTEGER NOT NULL,value TEXT NOT NULL,reason TEXT NOT NULL);
            CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;''')
        with gzip.open(source,'rb') as stream:
            while raw:=stream.readline(MAX_LINE+1):
                if len(raw)>MAX_LINE:raise ValueError('Oversized upstream record')
                line+=1
                if b'"redirects"' not in raw:continue
                row=json.loads(raw);language=row.get('lang_code');head=clean(row.get('word',''))
                if language not in (*LANGUAGES,'sw') or not form_ok(head):continue
                for value in row.get('redirects',[]):
                    if not isinstance(value,str) or not form_ok(clean(value)):
                        db.execute('INSERT INTO rejected VALUES (?,?,?)',(line,canonical(value),'unsupported-lexical-form'))
                        counts['rejected']+=1
                        continue
                    before=db.total_changes
                    db.execute('INSERT OR IGNORE INTO redirects VALUES (?,?,?,?)',(line,language,head,clean(value)))
                    counts[language]+=db.total_changes-before
        metadata=dict(schema='vipi-native-redirects-1',upstream_sha256=pin['source_sha256'],
            compiler_sha256=digest_file(Path(__file__)),source_entries=line,license='CC-BY-SA-4.0',
            provenance='Exact upstream redirects field and full-file line identity; no inferred alias or stem.')
        db.executemany('INSERT INTO metadata VALUES (?,?)',[(k,canonical(v)) for k,v in metadata.items()]);db.commit()
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    receipt=dict(**metadata,complete_source_scan=True,counts=dict(counts),sha256=digest_file(path),bytes=path.stat().st_size,seconds=round(time.monotonic()-start,2))
    (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(canonical(receipt),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();build(a.source,a.output)
