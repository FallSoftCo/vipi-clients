#!/usr/bin/env python3
"""Compile explicitly assessed mappings into signed, indexed native context packs.

Finite source variants are enumerated at build time. No approximate retrieval,
invented target text, or automatic linguistic approval occurs here. Qualification
signing keys are ephemeral and never become release trust anchors.
"""
import argparse
import itertools
import json
from pathlib import Path
import re
import sqlite3
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from build_wiktextract import canonical, digest_file, NON_ROMAN
from context_patterns import match_pattern
from mapping_catalog import digest, validate

POLICY='reviewed-finite-context-1'
SCHEMA='''
PRAGMA application_id=1447645257;
PRAGMA user_version=5;
PRAGMA temp_store=FILE;
PRAGMA foreign_keys=ON;
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE mappings(id TEXT PRIMARY KEY,payload TEXT NOT NULL,evidence TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE context_inputs(input TEXT NOT NULL,mapping_id TEXT NOT NULL REFERENCES mappings(id),
 PRIMARY KEY(input,mapping_id)) WITHOUT ROWID;
'''


def utf16(text): return len(text.encode('utf-16-le'))//2


def compile_record(envelope):
    record=envelope['record'];validate(record);sha=digest(record)
    if envelope.get('sha256')!=sha: raise ValueError('Changed assessed record')
    approved=[]
    for assessment in envelope['assessments']:
        if assessment.get('schema')!='vipi-mapping-review-1' or assessment.get('record_sha256')!=sha:
            raise ValueError('Wrong assessment binding')
        if assessment.get('verdict')!='reviewed': continue
        checks=assessment.get('checks',{})
        if assessment.get('assessment_kind') not in ('author_assessment','independent_assessment'):
            raise ValueError('Assessment origin required')
        reviewer=assessment.get('reviewer')
        if not isinstance(reviewer,str) or not reviewer.strip():raise ValueError('Named assessment required')
        if reviewer==record['provenance']['author'] and assessment['assessment_kind']!='author_assessment':
            raise ValueError('Author assessment cannot be labelled independent')
        evidence=assessment.get('evidence')
        if not isinstance(evidence,list) or not evidence:raise ValueError('Assessment evidence required')
        for item in evidence:
            if (not isinstance(item,dict) or not re.fullmatch('[a-f0-9]{64}',str(item.get('sha256','')))
                or not isinstance(item.get('description'),str) or not item['description'].strip()):
                raise ValueError('Content-addressed assessment evidence required')
        if any(checks.get(k)!='pass' for k in ('meaning','usage','grammar_scope','provenance')):
            raise ValueError('Incomplete assessment')
        required=record['target_language'] in NON_ROMAN
        if checks.get('reading')!=('pass' if required else 'not_required') or (required and not record['reading']):
            raise ValueError('Unassessed reading')
        approved.append(assessment)
    if not approved: raise ValueError('Unreviewed record')
    original=record['source_context'];start,end=record['source_span']
    parts=record['usage'].get('context_pattern')
    if parts is None:
        parts=([{'literal':original[:start]}] if start else [])+[{'focus':record['source']}]
        if end<len(original):parts.append({'literal':original[end:]})
    if match_pattern(original,parts)!=(start,end): raise ValueError('Invalid source scope')
    choices=[p['slot'] if 'slot' in p else [next(iter(p.values()))] for p in parts]
    count=1
    for values in choices:count*=len(values)
    if count>4096:raise ValueError('Finite pattern expansion exceeds pack bound')
    variants=sorted(set(''.join(values) for values in itertools.product(*choices)))
    for variant in variants:
        if utf16(variant)>16384 or match_pattern(variant,parts) is None:raise ValueError('Ambiguous source variant')
    target_context=record['target_context'];a,b=record['target_span']
    payload={'id':record['logical_id'],'meaning':record['meaning'],'source_language':record['source_language'],
        'target_language':record['target_language'],'parts':parts,'target':record['target'],'reading':record['reading'],
        'target_context':target_context,'target_span':[utf16(target_context[:a]),utf16(target_context[:b])],
        'record_sha256':sha}
    if len(canonical(payload).encode())>32768:raise ValueError('Native payload exceeds bound')
    return payload,variants


def load_export(folder):
    manifest=json.loads((folder/'manifest.json').read_text());path=folder/'records.jsonl'
    if manifest.get('schema')!='vipi-reviewed-mapping-export-1' or manifest.get('release_ready') is not False:
        raise ValueError('Expected internal reviewed export')
    if manifest['records_sha256']!=digest_file(path):raise ValueError('Changed export')
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    if len(rows)!=manifest['records'] or len({r['record']['logical_id'] for r in rows})!=len(rows):
        raise ValueError('Wrong count or duplicate identity')
    if not rows:raise ValueError('Empty reviewed export')
    return manifest,rows


def export_pair(rows,source,target,output,revision,key,key_id,source_manifest):
    output.mkdir(parents=True,exist_ok=False);database=output/'contexts.sqlite';variants=0
    with sqlite3.connect(database) as db:
        db.executescript(SCHEMA)
        for row in rows:
            payload,inputs=compile_record(row)
            if (payload['source_language'],payload['target_language'])!=(source,target):raise ValueError('Wrong pair')
            db.execute('INSERT INTO mappings VALUES (?,?,?)',(payload['id'],canonical(payload),canonical(row)))
            db.executemany('INSERT INTO context_inputs VALUES (?,?)',[(text,payload['id']) for text in inputs]);variants+=len(inputs)
        if db.execute('SELECT count(*) FROM (SELECT input FROM context_inputs GROUP BY input HAVING count(*)>256)').fetchone()[0]:
            raise ValueError('Native shortlist bound exceeded; never truncate conflicting claims')
        metadata={'schema':'vipi-reviewed-context-1','pack_id':source+'-'+target,
            'source_language':source,'target_language':target,'context_policy':POLICY}
        db.executemany('INSERT INTO metadata VALUES (?,?)',metadata.items());db.commit();db.execute('VACUUM')
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Invalid context database')
    if not 512<=database.stat().st_size<=67108864:raise ValueError('Context pack size exceeds bound')
    manifest=dict(metadata,schema_version=5,revision=revision,normalization='exact-utf16',file='contexts.sqlite',
        bytes=database.stat().st_size,sha256=digest_file(database),mappings=len(rows),indexed_variants=variants,
        export_sha256=source_manifest['records_sha256'],through_sequence=source_manifest['through_sequence'],
        key_id=key_id,signature_algorithm='ECDSA-P256-SHA256',compiler_sha256=digest_file(Path(__file__)),
        release_ready=False,quality='explicitly-assessed-development-contexts')
    encoded=canonical(manifest).encode();signature=key.sign(encoded,ec.ECDSA(hashes.SHA256()))
    key.public_key().verify(signature,encoded,ec.ECDSA(hashes.SHA256()))
    (output/'manifest.json').write_bytes(encoded);(output/'manifest.sig').write_bytes(signature)
    (output/'ATTRIBUTION.txt').write_text('Exact source provenance and content-bound assessments are retained in mappings.evidence.\n'
        'Finite source variants are indexed; target text is never interpolated. This is development qualification, not release acceptance.\n')
    return manifest


def main(a):
    if a.revision<1:raise ValueError('Positive revision required')
    manifest,rows=load_export(a.input)
    # This path currently qualifies data plumbing only. Release signing remains
    # separate until the exported contexts pass pair-level acceptance.
    key=ec.generate_private_key(ec.SECP256R1());a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'signing-public-key.der').write_bytes(key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo))
    pairs={}
    for row in rows:
        r=row['record'];pairs.setdefault((r['source_language'],r['target_language']),[]).append(row)
    results=[export_pair(values,s,t,a.output/(s+'-'+t),a.revision,key,a.key_id,manifest) for (s,t),values in sorted(pairs.items())]
    receipt={'schema':'vipi-reviewed-context-build-1','qualification_only_key':True,'private_key_written':False,
        'release_ready':False,'records':len(rows),'pairs':results,'bytes':sum(r['bytes'] for r in results),
        'export_sha256':manifest['records_sha256'],'compiler_sha256':digest_file(Path(__file__))}
    (a.output/'receipt.json').write_text(canonical(receipt)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k!='pairs'}|{'pairs':len(results)}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--revision',type=int,required=True);p.add_argument('--key-id',required=True)
    main(p.parse_args())
