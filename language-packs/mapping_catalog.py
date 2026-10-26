#!/usr/bin/env python3
"""Incremental authoring ledger. This database is not a client language pack.

Inputs are immutable/versioned evidence. Checkpoints and records commit together;
changing content creates a new revision whose linguistic review starts again.
Only explicitly reviewed current revisions can enter an export. Export is still
subject to pair-level acceptance and the existing signed-pack release process.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from build_wiktextract import LANGUAGES, NON_ROMAN, canonical, digest_file, form_ok, readable_roman
from context_hints import lookup_key
from context_patterns import validate_pattern,validate_frames

SCHEMA = '''
CREATE TABLE imports(id TEXT PRIMARY KEY, manifest TEXT NOT NULL, generation INTEGER NOT NULL UNIQUE,
 checkpoint INTEGER NOT NULL DEFAULT 0, complete INTEGER NOT NULL DEFAULT 0) WITHOUT ROWID;
CREATE TABLE revisions(sha256 TEXT PRIMARY KEY, logical_id TEXT NOT NULL,
 source_language TEXT NOT NULL, target_language TEXT NOT NULL, source_key TEXT NOT NULL,
 payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'candidate'
 CHECK(state IN ('candidate','reviewed','rejected','quarantined'))) WITHOUT ROWID;
CREATE INDEX revision_lookup ON revisions(source_language,target_language,source_key);
CREATE TABLE heads(logical_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL REFERENCES revisions(sha256),
 generation INTEGER NOT NULL) WITHOUT ROWID;
CREATE TABLE evidence(sha256 TEXT NOT NULL REFERENCES revisions(sha256),
 import_id TEXT NOT NULL REFERENCES imports(id), ordinal INTEGER NOT NULL,
 PRIMARY KEY(import_id,ordinal)) WITHOUT ROWID;
CREATE TABLE reviews(id TEXT PRIMARY KEY, record_sha256 TEXT NOT NULL REFERENCES revisions(sha256),
 reviewer TEXT NOT NULL, verdict TEXT NOT NULL, report TEXT NOT NULL, recorded_at INTEGER NOT NULL) WITHOUT ROWID;
CREATE TABLE changes(sequence INTEGER PRIMARY KEY AUTOINCREMENT, logical_id TEXT NOT NULL,
 record_sha256 TEXT NOT NULL REFERENCES revisions(sha256), action TEXT NOT NULL);
'''


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def adapter_identity():
    return {'adapter_sha256':digest_file(Path(__file__)),
            'adapter_dependencies':{name:digest_file(Path(__file__).with_name(name)) for name in
                                    ('build_wiktextract.py','context_hints.py','context_patterns.py')}}


def validate(record):
    if record.get('schema') != 'vipi-contextual-mapping-1':
        raise ValueError('Unsupported mapping schema')
    source, target = record.get('source_language'), record.get('target_language')
    if source not in LANGUAGES or target not in LANGUAGES or source == target:
        raise ValueError('Invalid mapping direction')
    if not isinstance(record.get('logical_id'), str) or not 1 <= len(record['logical_id']) <= 256:
        raise ValueError('Stable logical identity required')
    for field in ('source', 'target'):
        if not isinstance(record.get(field), str) or not form_ok(record[field]):
            raise ValueError('Invalid lexical surface')
    for side in ('source', 'target'):
        context = record.get(side+'_context'); span = record.get(side+'_span')
        if not isinstance(context,str) or not 0 < len(context) <= 4096:
            raise ValueError('Bounded context required')
        if (not isinstance(span,list) or len(span)!=2 or any(type(i) is not int for i in span)
            or not 0 <= span[0] < span[1] <= len(context)
            or context[span[0]:span[1]] != record[side]):
            raise ValueError('Exact independently bounded focus required')
    reading = record.get('reading')
    if not isinstance(reading,str) or (reading and readable_roman(reading) != reading):
        raise ValueError('Invalid readable transliteration')
    if not isinstance(record.get('meaning'),str) or not record['meaning'].strip():
        raise ValueError('Meaning required')
    if not isinstance(record.get('usage'),dict):
        raise ValueError('Usage evidence required')
    validate_pattern(record)
    validate_frames(record)
    provenance=record.get('provenance')
    if not isinstance(provenance,dict) or not provenance.get('author') or not provenance.get('license'):
        raise ValueError('Authorship and license provenance required')
    if len(canonical(record).encode()) > 32768:
        raise ValueError('Mapping record exceeds bound')


class Catalog:
    def __init__(self, path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.path, isolation_level=None)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA busy_timeout=5000')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA temp_store=FILE')
        try:
            with self.transaction():
                version=self.db.execute('PRAGMA user_version').fetchone()[0]
                if version==0:
                    for statement in SCHEMA.split(';'):
                        if statement.strip(): self.db.execute(statement)
                    self.db.execute('PRAGMA user_version=1')
                elif version!=1: raise ValueError('Unsupported authoring catalog')
        except BaseException:
            self.db.close(); raise

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK'); raise

    def register(self, manifest):
        identifier=digest(manifest)
        with self.transaction():
            generation=self.db.execute('SELECT coalesce(max(generation),0)+1 FROM imports').fetchone()[0]
            self.db.execute('INSERT OR IGNORE INTO imports(id,manifest,generation) VALUES (?,?,?)', (identifier,canonical(manifest),generation))
        return identifier

    def position(self, identifier):
        row=self.db.execute('SELECT checkpoint,complete FROM imports WHERE id=?',(identifier,)).fetchone()
        if row is None: raise ValueError('Unknown input')
        return row['checkpoint'],bool(row['complete'])

    def ingest(self, identifier, after, rows, complete=False):
        """rows are (monotonic input ordinal, immutable mapping) tuples."""
        inserted=0
        with self.transaction():
            checkpoint, finished=self.position(identifier)
            if checkpoint!=after or finished: raise ValueError('Stale or completed import cursor')
            generation=self.db.execute('SELECT generation FROM imports WHERE id=?',(identifier,)).fetchone()[0]
            for ordinal, record in rows:
                if type(ordinal) is not int or ordinal <= checkpoint: raise ValueError('Non-monotonic input')
                validate(record)
                sha=digest(record); logical=record['logical_id']
                before=self.db.total_changes
                self.db.execute('INSERT OR IGNORE INTO revisions(sha256,logical_id,source_language,target_language,source_key,payload) VALUES (?,?,?,?,?,?)',
                    (sha,logical,record['source_language'],record['target_language'],lookup_key(record['source'],record['source_language']),canonical(record)))
                is_new=self.db.total_changes>before
                inserted+=int(is_new)
                old=self.db.execute('SELECT sha256,generation FROM heads WHERE logical_id=?',(logical,)).fetchone()
                # Resuming an older input cannot roll a newer head back. Nor
                # can reimporting an already-known historical revision revive
                # it after a correction. Its provenance is still retained.
                advance=old is None or (generation>=old['generation'] and is_new and old['sha256']!=sha)
                if advance:
                    self.db.execute('INSERT INTO heads VALUES (?,?,?) ON CONFLICT(logical_id) DO UPDATE SET sha256=excluded.sha256,generation=excluded.generation',(logical,sha,generation))
                    self.db.execute('INSERT INTO changes(logical_id,record_sha256,action) VALUES (?,?,?)',(logical,sha,'candidate_revision'))
                elif old['sha256']==sha and generation>old['generation']:
                    self.db.execute('UPDATE heads SET generation=? WHERE logical_id=?',(generation,logical))
                self.db.execute('INSERT INTO evidence VALUES (?,?,?)',(sha,identifier,ordinal))
                checkpoint=ordinal
            self.db.execute('UPDATE imports SET checkpoint=?,complete=? WHERE id=?',(checkpoint,int(complete),identifier))
        return {'inserted':inserted,'checkpoint':checkpoint,'complete':complete}

    def review(self, report):
        """Record an explicit assessment and its origin; retrieval is not review."""
        identifier=digest(report)
        with self.transaction():
            if self.db.execute('SELECT 1 FROM reviews WHERE id=?',(identifier,)).fetchone(): return
            if report.get('schema')!='vipi-mapping-review-1': raise ValueError('Unsupported review schema')
            sha=report.get('record_sha256'); row=self.db.execute('SELECT * FROM revisions WHERE sha256=?',(sha,)).fetchone()
            if row is None: raise ValueError('Unknown exact revision')
            record=json.loads(row['payload']); reviewer=report.get('reviewer'); verdict=report.get('verdict')
            if not isinstance(reviewer,str) or not reviewer.strip() or verdict not in ('reviewed','rejected','quarantined'):
                raise ValueError('Explicit reviewer and verdict required')
            if not report.get('evidence') or not isinstance(report['evidence'],list): raise ValueError('Review evidence required')
            for item in report['evidence']:
                sha_value=item.get('sha256','') if isinstance(item,dict) else ''
                if not isinstance(sha_value,str) or len(sha_value)!=64 or any(c not in '0123456789abcdef' for c in sha_value) or not item.get('description'):
                    raise ValueError('Content-addressed review evidence required')
            if verdict=='reviewed':
                checks=report.get('checks',{})
                origin=report.get('assessment_kind')
                if origin not in ('author_assessment','independent_assessment'):
                    raise ValueError('Assessment origin required')
                if reviewer==record['provenance']['author'] and origin!='author_assessment':
                    raise ValueError('Author assessment cannot be labelled independent')
                if any(checks.get(gate)!='pass' for gate in ('meaning','usage','grammar_scope','provenance')):
                    raise ValueError('Incomplete linguistic review')
                if record['usage'].get('context_extent')=='local_phrase' and checks.get('context_frame_scope')!='pass':
                    raise ValueError('Local phrase generalization has not passed explicit review')
                required=record['target_language'] in NON_ROMAN
                if checks.get('reading')!=('pass' if required else 'not_required') or (required and not record['reading']):
                    raise ValueError('Readable target has not passed review')
            self.db.execute('INSERT INTO reviews VALUES (?,?,?,?,?,?)',(identifier,sha,reviewer,verdict,canonical(report),int(time.time())))
            self.db.execute('UPDATE revisions SET state=? WHERE sha256=?',(verdict,sha))
            self.db.execute('INSERT INTO changes(logical_id,record_sha256,action) VALUES (?,?,?)',(row['logical_id'],sha,verdict))

    def stats(self):
        return {'revisions':self.db.execute('SELECT count(*) FROM revisions').fetchone()[0],
            'current_records':self.db.execute('SELECT count(*) FROM heads').fetchone()[0],
            'states':dict(self.db.execute('SELECT r.state,count(*) FROM heads h JOIN revisions r ON r.sha256=h.sha256 GROUP BY r.state')),
            'imports':self.db.execute('SELECT count(*) FROM imports').fetchone()[0],
            'completed_imports':self.db.execute('SELECT count(*) FROM imports WHERE complete=1').fetchone()[0],
            'sequence':self.db.execute('SELECT coalesce(max(sequence),0) FROM changes').fetchone()[0]}

    def export_reviewed(self, directory, extent=None):
        """Internal staging export; existing native release gates still apply."""
        if extent not in (None,'exact_context','local_phrase'):raise ValueError('Invalid export extent')
        directory=Path(directory); directory.mkdir(parents=True,exist_ok=False)
        count=0; path=directory/'records.jsonl'
        with self.transaction(),path.open('x') as output:
            for row in self.db.execute("SELECT r.sha256,r.payload FROM heads h JOIN revisions r ON r.sha256=h.sha256 WHERE r.state='reviewed' ORDER BY h.logical_id"):
                record=json.loads(row['payload'])
                if extent is not None and record['usage'].get('context_extent','exact_context')!=extent:continue
                assessments=[json.loads(item[0]) for item in self.db.execute('SELECT report FROM reviews WHERE record_sha256=? ORDER BY recorded_at,id',(row['sha256'],))]
                output.write(canonical({'sha256':row['sha256'],'record':record,'assessments':assessments})+'\n'); count+=1
            sequence=self.stats()['sequence']
        manifest={'schema':'vipi-reviewed-mapping-export-1','records':count,'through_sequence':sequence,
            'records_sha256':digest_file(path),'release_ready':False,
            'remaining_gates':['Independent pair-level held-out precision and useful coverage.','Native pack compilation/signing and on-device qualification.']}
        (directory/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        return manifest


def contextual_record(row, receipt):
    identity=['wiktextract-example',receipt['source_selection_sha256'],row['source_line'],row['sense_index'],row['example_index'],row['source_language'],row['target_language']]
    return {'schema':'vipi-contextual-mapping-1','logical_id':digest(identity),
        'source_language':row['source_language'],'target_language':row['target_language'],
        'source':row['source'],'target':row['target'],'reading':row['reading'],
        'source_context':row['source_context'],'target_context':row['target_context'],
        'source_span':[row['source_start'],row['source_end']],'target_span':[row['target_start'],row['target_end']],
        'meaning':row['gloss'] or 'Unlabelled attested example; meaning review required',
        'usage':json.loads(row['usage_evidence']),
        'provenance':{'author':'Wiktionary contributors','license':receipt['license'],'url':row['source_url'],
            'source_selection_sha256':receipt['source_selection_sha256'],'upstream_sha256':receipt['upstream_sha256'],
            'source_line':row['source_line'],'sense_index':row['sense_index'],'example_index':row['example_index']}}


def import_index(catalog, folder, batch_size, max_batches):
    receipt=json.loads((folder/'receipt.json').read_text()); path=folder/'contexts.sqlite'
    if receipt.get('schema')!='vipi-context-example-research-2' or not receipt.get('complete_source_scan'):
        raise ValueError('Complete context index schema 2 required')
    if path.stat().st_size!=receipt['bytes'] or digest_file(path)!=receipt['sha256']:
        raise ValueError('Input index integrity mismatch')
    manifest={'kind':'context-index','sha256':receipt['sha256'],'receipt_sha256':digest_file(folder/'receipt.json'),
              **adapter_identity(),'cursor_unit':'row_id'}
    identifier=catalog.register(manifest); completed_batches=0
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as source:
        source.row_factory=sqlite3.Row
        while not max_batches or completed_batches<max_batches:
            checkpoint,complete=catalog.position(identifier)
            if complete: break
            rows=source.execute('SELECT * FROM examples WHERE id>? ORDER BY id LIMIT ?', (checkpoint,batch_size)).fetchall()
            end=not rows or source.execute('SELECT 1 FROM examples WHERE id>? LIMIT 1',(rows[-1]['id'],)).fetchone() is None
            result=catalog.ingest(identifier,checkpoint,[(row['id'],contextual_record(row,receipt)) for row in rows],end)
            completed_batches+=1
            print(json.dumps({'import_id':identifier,'batch':completed_batches,**result}),flush=True)
    return identifier


def import_records(catalog, path, batch_size, max_batches):
    manifest={'kind':'authored-records-jsonl','sha256':digest_file(path),
              'bytes':path.stat().st_size,**adapter_identity(),
              'cursor_unit':'byte_offset'}
    identifier=catalog.register(manifest); batches=0
    with path.open('rb') as stream:
        while not max_batches or batches<max_batches:
            checkpoint,complete=catalog.position(identifier)
            if complete: break
            stream.seek(checkpoint); rows=[]
            for _ in range(batch_size):
                raw=stream.readline(32770)
                if not raw: break
                if len(raw)>32769 or not raw.endswith(b'\n'): raise ValueError('Bounded complete JSONL records required')
                rows.append((stream.tell(),json.loads(raw)))
            complete=stream.tell()==manifest['bytes']
            result=catalog.ingest(identifier,checkpoint,rows,complete)
            batches+=1
            print(json.dumps({'import_id':identifier,'batch':batches,**result}),flush=True)
    return identifier


def main(args):
    if args.batch_size<1 or args.batch_size>10000 or args.max_batches<0: raise ValueError('Invalid batch bound')
    if args.command in ('import-index','import-records','review') and args.input is None: raise ValueError('--input required')
    if args.command=='export-reviewed' and args.output is None: raise ValueError('--output required')
    catalog=Catalog(args.catalog)
    try:
        if args.command=='import-index': import_index(catalog,args.input,args.batch_size,args.max_batches)
        elif args.command=='import-records': import_records(catalog,args.input,args.batch_size,args.max_batches)
        elif args.command=='review': catalog.review(json.loads(args.input.read_text()))
        elif args.command=='export-reviewed': print(json.dumps(catalog.export_reviewed(args.output,args.extent)))
        print(json.dumps(catalog.stats()),flush=True)
    finally: catalog.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['import-index','import-records','status','review','export-reviewed'])
    parser.add_argument('--catalog',type=Path,required=True)
    parser.add_argument('--input',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--extent',choices=['exact_context','local_phrase'])
    parser.add_argument('--batch-size',type=int,default=1000)
    parser.add_argument('--max-batches',type=int,default=0)
    main(parser.parse_args())
