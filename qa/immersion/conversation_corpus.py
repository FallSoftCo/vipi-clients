#!/usr/bin/env python3
"""Reproducible public-corpus acquisition and development/reference partitioning.

This is an authoring tool, not a runtime dependency. Linked Tatoeba sentences are
references, not certified translations or samples of private-chat frequency.
Only direct links are translation candidates; transitive links only prevent
related examples leaking across development and reserved evaluation partitions.
"""
import argparse
from array import array
import bz2
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import tarfile
import time
import unicodedata
import urllib.request

LANGUAGES = dict(zip(('eng','spa','fra','deu','ita','por','ara','cmn','jpn','kor'),
                     ('en','es','fr','de','it','pt','ar','zh','ja','ko')))
BASE = 'https://downloads.tatoeba.org/exports/'
SPLIT_RECIPE = 'vipi-tatoeba-components-1:85-development:15-reserved'


def sha_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''): h.update(block)
    return h.hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(path)


def key(text):
    # Preserve accents, punctuation, and script. Whitespace and casing alone
    # must not put the same example into both partitions.
    return ' '.join(unicodedata.normalize('NFC', text).casefold().split())


def acquire(folder):
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder/'sources.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    else:
        names = [f'per_language/{code}/{code}_sentences_detailed.tsv.bz2' for code in LANGUAGES]
        names += ['links.tar.bz2', 'tags_detailed.tar.bz2', 'tag_metadata.csv', 'transcriptions.tar.bz2']
        assets = []
        for name in names:
            with urllib.request.urlopen(urllib.request.Request(BASE+name, method='HEAD'), timeout=60) as r:
                assets.append({'name':name, 'file':name.rsplit('/',1)[-1], 'url':BASE+name,
                    'bytes':int(r.headers['Content-Length']), 'etag':r.headers['ETag'],
                    'last_modified':r.headers['Last-Modified']})
        # Freeze before any sentence is read. Mutable upstream exports must not
        # silently change halfway through a resumed acquisition.
        manifest = {'schema':'vipi-tatoeba-sources-1', 'assets':assets,
            'license':'CC BY 2.0 FR', 'license_source':'https://tatoeba.org/en/downloads',
            'attribution':'Tatoeba contributors; individual usernames and sentence IDs retained',
            'split_recipe':SPLIT_RECIPE, 'upstream_cryptographic_checksums_available':False}
        write_json(manifest_path,manifest)
    if manifest.get('split_recipe') != SPLIT_RECIPE: raise ValueError('Wrong source partition recipe')
    receipt = []
    for item in manifest['assets']:
        path = folder/item['file']; checksum = path.with_suffix(path.suffix+'.sha256')
        if path.exists():
            if not checksum.exists() or path.stat().st_size != item['bytes'] or sha_file(path) != checksum.read_text().strip():
                raise ValueError('Existing asset integrity failure: '+path.name)
        else:
            partial = path.with_suffix(path.suffix+'.part')
            req = urllib.request.Request(item['url'], headers={'If-Match':item['etag']})
            with urllib.request.urlopen(req,timeout=120) as response, partial.open('wb') as output:
                if response.headers.get('ETag') != item['etag'] or response.headers.get('Last-Modified') != item['last_modified']:
                    raise ValueError('Upstream changed after metadata freeze')
                size = 0
                while block := response.read(1<<20):
                    size += len(block)
                    if size > item['bytes']: raise ValueError('Download exceeds frozen size')
                    output.write(block)
            if size != item['bytes']: raise ValueError('Incomplete download')
            checksum.write_text(sha_file(partial)+'\n'); partial.replace(path)
        receipt.append({**item,'sha256':sha_file(path)})
        print(json.dumps({'acquired':path.name,'bytes':item['bytes']}),flush=True)
    write_json(folder/'receipt.json',{'schema':'vipi-tatoeba-acquisition-1',
        'manifest_sha256':sha_file(manifest_path),'assets':receipt,
        'checksum_scope':'Locally measured against frozen HTTP metadata; not publisher-signed'})


def lines(path, member=None, max_bytes=2_000_000_000):
    """Bounded streaming reads; no archive paths are extracted."""
    def read(stream):
        count = 0
        while raw := stream.readline(65537):
            count += len(raw)
            if len(raw)>65536 or count>max_bytes: raise ValueError('Corpus size bound exceeded')
            yield raw.decode('utf-8').rstrip('\r\n')
    if member:
        with tarfile.open(path,'r|bz2') as archive:
            found = False
            for entry in archive:
                if entry.name != member or not entry.isfile() or entry.size>max_bytes:
                    raise ValueError('Unexpected archive member')
                if found: raise ValueError('Duplicate archive member')
                found = True
                with archive.extractfile(entry) as stream: yield from read(stream)
            if not found: raise ValueError('Missing archive member')
    else:
        opener = bz2.open if path.suffix=='.bz2' else open
        with opener(path,'rb') as stream: yield from read(stream)


class Components:
    def __init__(self): self.parent = array('I',[0])
    def root(self,value):
        if not 0<value<40_000_000: raise ValueError('Unexpected sentence ID')
        if value>=len(self.parent):
            end = min(40_000_000, ((value//100000)+1)*100000)
            self.parent.extend(range(len(self.parent),end))
        parent = self.parent
        while parent[value] != value:
            parent[value] = parent[parent[value]]; value = parent[value]
        return value
    def union(self,a,b):
        a,b=self.root(a),self.root(b)
        if a!=b: self.parent[max(a,b)] = min(a,b)


def partition(component):
    value = hashlib.sha256((SPLIT_RECIPE+':'+str(component)).encode()).digest()
    return 'reserved' if int.from_bytes(value[:8],'big')%100<15 else 'development'


def tag_row(line):
    # Publisher SQL: SELECT ts.tag_id, ts.sentence_id, u.username, ts.added_time.
    # Unlike tags.csv, the detailed export puts the tag ID first.
    fields=line.split('\t')
    if len(fields)!=4: raise ValueError('Unexpected detailed tag fields')
    return int(fields[1]),int(fields[0]),fields[2],fields[3]


def import_tags(db,folder,selected):
    count=0
    for line in lines(folder/'tags_detailed.tar.bz2','tags_detailed.csv'):
        row=tag_row(line)
        if row[0] in selected:
            db.execute('INSERT INTO tags VALUES (?,?,?,?)',row);count+=1
    if db.execute('SELECT count(*) FROM tags t LEFT JOIN tag_metadata m ON m.id=t.tag WHERE m.id IS NULL').fetchone()[0]:
        raise ValueError('Detailed tag references absent metadata')
    return count


def repair_tags(folder,old,output):
    """Correct schema interpretation without repeating immutable graph work."""
    if output.exists():raise ValueError('Use a new output revision')
    prior=json.loads((old.parent/'receipt.json').read_text())
    if sha_file(old)!=prior['sha256']:raise ValueError('Prior index integrity failure')
    acquisition=json.loads((folder/'receipt.json').read_text())
    tag_asset=next(a for a in acquisition['assets'] if a['file']=='tags_detailed.tar.bz2')
    if sha_file(folder/tag_asset['file'])!=tag_asset['sha256']:raise ValueError('Tag source integrity failure')
    output.mkdir(parents=True);path=output/'corpus.sqlite'
    with sqlite3.connect(old.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as source,sqlite3.connect(path) as db:
        source.backup(db);db.execute('DELETE FROM tags')
        selected={r[0] for r in db.execute('SELECT id FROM sentences')}
        count=import_tags(db,folder,selected)
        metadata={k:v for k,v in prior.items() if k not in ('sha256','bytes')}
        metadata.update(tags_schema='tag_id,sentence_id,username,added_time',tag_rows=count,
            parent_index_sha256=prior['sha256'],repair_builder_sha256=sha_file(Path(__file__)),
            tag_schema_source=json.loads((folder/'export-schema-source.json').read_text()))
        db.execute('UPDATE metadata SET value=? WHERE key=?',(json.dumps(metadata),'receipt'));db.commit()
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Repaired index integrity failure')
    metadata.update(bytes=path.stat().st_size,sha256=sha_file(path));write_json(output/'receipt.json',metadata)
    print(json.dumps({'tags':count,'bytes':metadata['bytes'],'sha256':metadata['sha256']}))


def build(folder, output, known_catalog=None):
    if output.exists(): raise ValueError('Use a new output revision')
    receipt = json.loads((folder/'receipt.json').read_text())
    for item in receipt['assets']:
        if sha_file(folder/item['file']) != item['sha256']: raise ValueError('Source integrity failed')
    output.mkdir(parents=True)
    path=output/'corpus.sqlite'; db=sqlite3.connect(path)
    db.execute('PRAGMA temp_store=FILE')
    db.executescript('''CREATE TABLE sentences(id INTEGER PRIMARY KEY, language TEXT NOT NULL,
        text TEXT NOT NULL, owner TEXT NOT NULL, added TEXT, modified TEXT,
        normalized TEXT NOT NULL, component INTEGER, partition TEXT);
      CREATE TABLE links(a INTEGER NOT NULL,b INTEGER NOT NULL,PRIMARY KEY(a,b)) WITHOUT ROWID;
      CREATE TABLE tags(sentence INTEGER,tag INTEGER,owner TEXT,added TEXT);
      CREATE TABLE tag_metadata(id INTEGER PRIMARY KEY,name TEXT);
      CREATE TABLE transcriptions(sentence INTEGER,language TEXT,script TEXT,owner TEXT,text TEXT);
      CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);''')
    components=Components(); selected=set(); counts=Counter(); duplicates=0
    for code,language in LANGUAGES.items():
        rows=[]
        for line in lines(folder/f'{code}_sentences_detailed.tsv.bz2'):
            fields=line.split('\t')
            if len(fields)!=6 or fields[1]!=code or not fields[2]: raise ValueError('Invalid detailed sentence')
            identifier=int(fields[0]); selected.add(identifier)
            rows.append((identifier,language,fields[2],fields[3],fields[4],fields[5],key(fields[2])))
            counts[language]+=1
            if len(rows)==10000:
                db.executemany('INSERT INTO sentences VALUES (?,?,?,?,?,?,?,NULL,NULL)',rows); db.commit(); rows=[]
        db.executemany('INSERT INTO sentences VALUES (?,?,?,?,?,?,?,NULL,NULL)',rows); db.commit()
        print(json.dumps({'sentences':language,'count':counts[language]}),flush=True)
    db.execute('CREATE INDEX duplicate_lookup ON sentences(language,normalized)');db.commit()
    previous=None; first=None
    for identifier,language,normalized in db.execute('SELECT id,language,normalized FROM sentences ORDER BY language,normalized,id'):
        current=(language,normalized)
        if current==previous: components.union(first,identifier); duplicates+=1
        else: previous=current; first=identifier
    rows=[]; scanned=0
    for line in lines(folder/'links.tar.bz2','links.csv'):
        a,b=map(int,line.split('\t'));components.union(a,b);scanned+=1
        # Both orientations occur upstream. Canonical edges retain direct
        # equivalence without manufacturing English-pivot translations.
        if a in selected and b in selected and a<b: rows.append((a,b))
        if len(rows)>=10000:
            db.executemany('INSERT OR IGNORE INTO links VALUES (?,?)',rows);db.commit();rows=[]
    db.executemany('INSERT OR IGNORE INTO links VALUES (?,?)',rows);db.commit()
    known=set()
    if known_catalog:
        with sqlite3.connect(known_catalog.resolve().as_uri()+'?mode=ro',uri=True) as old:
            for payload, in old.execute('SELECT payload FROM revisions'):
                record=json.loads(payload)
                for side in ('source','target'): known.add((record[side+'_language'],key(record[side+'_context'])))
    contaminated=set()
    if known:
        for identifier,language,normalized in db.execute('SELECT id,language,normalized FROM sentences'):
            if (language,normalized) in known: contaminated.add(components.root(identifier))
    rows=[]; groups=Counter(); partitions=Counter()
    for identifier,language in db.execute('SELECT id,language FROM sentences'):
        root=components.root(identifier); split='development' if root in contaminated else partition(root)
        groups[root]+=1;partitions[language+':'+split]+=1;rows.append((root,split,identifier))
        if len(rows)==10000:
            db.executemany('UPDATE sentences SET component=?,partition=? WHERE id=?',rows);db.commit();rows=[]
    db.executemany('UPDATE sentences SET component=?,partition=? WHERE id=?',rows)
    db.execute('CREATE INDEX partition_lookup ON sentences(partition,language,id)');db.commit()
    for line in lines(folder/'tag_metadata.csv'):
        fields=line.split('\t')
        db.execute('INSERT INTO tag_metadata VALUES (?,?)',(int(fields[0]),fields[1]))
    tag_count=import_tags(db,folder,selected)
    db.commit()
    for line in lines(folder/'transcriptions.tar.bz2','transcriptions.csv'):
        fields=line.split('\t')
        if len(fields)!=5: raise ValueError('Unexpected transcription fields')
        if int(fields[0]) in selected: db.execute('INSERT INTO transcriptions VALUES (?,?,?,?,?)',fields)
    db.commit()
    db.execute('CREATE INDEX tags_sentence ON tags(sentence)');db.execute('CREATE INDEX readings_sentence ON transcriptions(sentence)')
    pairs=[{'source':a,'target':b,'direct_links':n} for a,b,n in db.execute('''SELECT s.language,t.language,count(*)
      FROM links l JOIN sentences s ON s.id=l.a JOIN sentences t ON t.id=l.b
      WHERE s.language!=t.language GROUP BY s.language,t.language''')]
    metadata={'schema':'vipi-conversation-reference-1','source_receipt_sha256':sha_file(folder/'receipt.json'),
        'builder_sha256':sha_file(Path(__file__)),'split_recipe':SPLIT_RECIPE,'counts':dict(counts),
        'tags_schema':'tag_id,sentence_id,username,added_time','tag_rows':tag_count,
        'partitions':dict(partitions),'translation_graph_edges_scanned':scanned,'direct_pair_counts_canonical_orientation':pairs,
        'duplicate_rows_grouped':duplicates,'component_count':len(groups),'largest_component_selected_sentences':max(groups.values()),
        'previously_seen_components_forced_into_development':len(contaminated),
        'known_catalog_sha256':sha_file(known_catalog) if known_catalog else None,
        'linguistic_acceptance':False,'runtime_integration':False,
        'limits':['Contributor sentence references are not representative private-chat frequencies.',
          'Reserved components have not been used for mapping expansion in this snapshot.',
          'Prior exposure outside the supplied catalog is not ruled out.',
          'Full sentence links and transcriptions do not certify lexical alignment or word readings.']}
    db.execute('INSERT INTO metadata VALUES (?,?)',('receipt',json.dumps(metadata)));db.commit()
    if db.execute('PRAGMA quick_check').fetchone()[0]!='ok': raise ValueError('SQLite integrity failure')
    db.close();metadata.update(bytes=path.stat().st_size,sha256=sha_file(path))
    write_json(output/'receipt.json',metadata)
    print(json.dumps(metadata),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['acquire','build','repair-tags'])
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path)
    p.add_argument('--known-catalog',type=Path);p.add_argument('--from-index',type=Path);args=p.parse_args()
    if args.command=='acquire': acquire(args.source)
    else:
        if args.output is None: p.error('--output required')
        if args.command=='repair-tags':
            if args.from_index is None:p.error('--from-index required')
            repair_tags(args.source,args.from_index,args.output)
        else:build(args.source,args.output,args.known_catalog)
