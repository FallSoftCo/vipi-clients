#!/usr/bin/env python3
"""Add pinned Swahili direct links without reading reserved sentence text.

This is a separate development supplement, not a repartition of the original
corpus. Duplicate Swahili sentences touching any reserved component are omitted.
Existing source exports and licenses remain independently pinned.
"""
import argparse
from collections import defaultdict,Counter
import json
from pathlib import Path
import sqlite3
from conversation_corpus import lines,key,sha_file,write_json


def build(args):
    args.output.mkdir(parents=True,exist_ok=False)
    sw_receipt=json.loads((args.swahili/'receipt.json').read_text())
    source=args.swahili/'swh_sentences_detailed.tsv.bz2'
    assert sha_file(source)==sw_receipt['sha256']
    original=json.loads((args.exports/'receipt.json').read_text())
    link_source=next(r for r in original['assets'] if r['file']=='links.tar.bz2')
    assert sha_file(args.exports/link_source['file'])==link_source['sha256']
    # The supplement and graph must come from the same weekly export date.
    assert sw_receipt['last_modified'][:16]==link_source['last_modified'][:16]
    sw={};duplicates=defaultdict(set)
    for line in lines(source):
        fields=line.split('\t');assert len(fields)==6 and fields[1]=='swh'
        identifier=int(fields[0]);sw[identifier]=fields;duplicates[key(fields[2])].add(identifier)
    links=set();foreign=set()
    for line in lines(args.exports/'links.tar.bz2','links.csv'):
        a,b=map(int,line.split('\t'))
        if a in sw and b not in sw:links.add((a,b));foreign.add(b)
        elif b in sw and a not in sw:links.add((b,a));foreign.add(a)
    corpus=sqlite3.connect(args.corpus.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    foreign=sorted(foreign);endpoints={}
    for offset in range(0,len(foreign),500):
        batch=foreign[offset:offset+500]
        for row in corpus.execute('SELECT id,language,component,partition FROM sentences WHERE id IN ('+','.join('?'*len(batch))+')',batch):
            endpoints[row[0]]=row
    related=defaultdict(set)
    for a,b in links:
        if b in endpoints:related[a].add(b)
    rejected=set();components={}
    for normalized,ids in duplicates.items():
        neighbors=set().union(*(related[i] for i in ids))
        if any(endpoints[n][3]!='development' for n in neighbors):
            rejected.update(ids);continue
        # No unconnected or newly inferred sentence enters development.
        if not neighbors or any(not related[i] for i in ids):rejected.update(ids);continue
        component=min(endpoints[n][2] for n in neighbors)
        for identifier in ids:components[identifier]=component
    retained=sorted((a,b) for a,b in links if a in components and b in endpoints and endpoints[b][3]=='development')
    wanted=set(b for a,b in retained);sw_ids=set(a for a,b in retained)
    db=sqlite3.connect(args.output/'corpus.sqlite')
    db.executescript('''PRAGMA temp_store=FILE;
        CREATE TABLE sentences(id INTEGER PRIMARY KEY,language TEXT NOT NULL,text TEXT NOT NULL,owner TEXT NOT NULL,
            added TEXT,modified TEXT,normalized TEXT NOT NULL,component INTEGER NOT NULL,partition TEXT NOT NULL);
        CREATE TABLE links(a INTEGER NOT NULL,b INTEGER NOT NULL,PRIMARY KEY(a,b)) WITHOUT ROWID;
        CREATE TABLE tags(sentence INTEGER,tag INTEGER,owner TEXT,added TEXT);
        CREATE TABLE tag_metadata(id INTEGER PRIMARY KEY,name TEXT);
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
        CREATE INDEX partition_lookup ON sentences(partition,language,id);''')
    for identifier in sorted(sw_ids):
        _,_,text,owner,added,modified=sw[identifier]
        db.execute('INSERT INTO sentences VALUES (?,?,?,?,?,?,?,?,?)',(identifier,'sw',text,owner,added,modified,key(text),components[identifier],'development'))
    ordered=sorted(wanted)
    for offset in range(0,len(ordered),500):
        batch=ordered[offset:offset+500]
        for row in corpus.execute("SELECT * FROM sentences WHERE partition='development' AND id IN ("+','.join('?'*len(batch))+')',batch):
            db.execute('INSERT INTO sentences VALUES (?,?,?,?,?,?,?,?,?)',row)
    db.executemany('INSERT INTO links VALUES (?,?)',(tuple(sorted(pair)) for pair in retained))
    db.executemany('INSERT INTO tag_metadata VALUES (?,?)',corpus.execute('SELECT id,name FROM tag_metadata'))
    selected=wanted|sw_ids
    # Use the frozen full publisher tag export; this includes Swahili tags
    # omitted by the earlier ten-language corpus.
    from conversation_corpus import tag_row
    for line in lines(args.exports/'tags_detailed.tar.bz2','tags_detailed.csv'):
        row=tag_row(line)
        if row[0] in selected:db.execute('INSERT INTO tags VALUES (?,?,?,?)',row)
    counts=dict(db.execute('SELECT language,count(*) FROM sentences GROUP BY language'))
    receipt=dict(schema='vipi-swahili-development-supplement-1',counts=counts,direct_links=len(retained),
        tags_schema='tag_id,sentence_id,username,added_time',swahili_source_sha256=sw_receipt['sha256'],
        graph_sha256=link_source['sha256'],parent_receipt_sha256=sha_file(args.corpus.parent/'receipt.json'),
        compiler_sha256=sha_file(Path(__file__)),reserved_sentence_text_read=False,
        excluded_sw_sentences=len(rejected),partition='development-only direct-neighbor supplement',
        duplicate_policy='All identical Swahili sentences touching a reserved component are excluded.',
        license='CC BY 2.0 FR',linguistic_acceptance=False)
    db.execute('INSERT INTO metadata VALUES (?,?)',('receipt',json.dumps(receipt)));db.commit()
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    db.close();corpus.close();receipt.update(bytes=(args.output/'corpus.sqlite').stat().st_size,sha256=sha_file(args.output/'corpus.sqlite'))
    write_json(args.output/'receipt.json',receipt)
    (args.output/'ATTRIBUTION.txt').write_text('Tatoeba contributors, CC BY 2.0 FR. Individual sentence owners retained.\n'
        'Sentence sources: https://tatoeba.org/en/sentences/show/{id}. Direct linked development supplement; no linguistic acceptance.\n')
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('swahili','exports','corpus','output'):p.add_argument('--'+name,type=Path,required=True)
    build(p.parse_args())
