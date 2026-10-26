#!/usr/bin/env python3
"""Compile explicitly assessed source/target phrase frames, never old scopes."""
import argparse
import itertools
import json
from pathlib import Path
import sqlite3
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
from build_wiktextract import canonical,digest_file
from context_patterns import frame_parts,match_pattern
from export_reviewed_contexts import assessed_record,load_export,utf16

POLICY='reviewed-bidirectional-phrase-and-unit-2'
SCHEMA='''
PRAGMA application_id=1447645257;
PRAGMA user_version=7;
PRAGMA temp_store=FILE;
PRAGMA foreign_keys=ON;
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE mappings(id TEXT PRIMARY KEY,payload TEXT NOT NULL,evidence TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE source_inputs(input TEXT NOT NULL,mapping_id TEXT NOT NULL REFERENCES mappings(id),PRIMARY KEY(input,mapping_id)) WITHOUT ROWID;
CREATE TABLE target_inputs(input TEXT NOT NULL,mapping_id TEXT NOT NULL REFERENCES mappings(id),PRIMARY KEY(input,mapping_id)) WITHOUT ROWID;
'''


def variants(parts,lexical_unit=False):
    if lexical_unit:
        if len(parts)!=1 or set(parts[0])!={'focus'} or not 0<utf16(parts[0]['focus'])<=128:
            raise ValueError('Invalid complete lexical unit')
        return [parts[0]['focus']]
    choices=[p['slot'] if 'slot' in p else [next(iter(p.values()))] for p in parts]
    count=1
    for values in choices:count*=len(values)
    if count>4096:raise ValueError('Frame expansion exceeds bound')
    values=sorted(set(''.join(row) for row in itertools.product(*choices)))
    for value in values:
        if utf16(value)>256 or match_pattern(value,parts) is None:raise ValueError('Ambiguous/oversize phrase variant')
    return values


def compile_record(envelope):
    record,sha,assessments=assessed_record(envelope)
    if record['usage'].get('context_extent')!='local_phrase':raise ValueError('Explicit phrase extent required')
    if not any(a['checks'].get('context_frame_scope')=='pass' for a in assessments):
        raise ValueError('Phrase generalization requires its own assessment')
    unit=record['usage'].get('lexical_unit',False)
    if unit and not any(a['checks'].get('lexical_unit_scope')=='pass' for a in assessments):
        raise ValueError('Complete lexical units require their own assessment')
    source=frame_parts(record,'source');target=frame_parts(record,'target')
    payload={'id':record['logical_id'],'meaning':record['meaning'],'source_language':record['source_language'],
        'target_language':record['target_language'],'source_parts':source,'target_parts':target,
        'source':record['source'],'target':record['target'],'reading':record['reading'],'record_sha256':sha,
        'lexical_unit':unit}
    if len(canonical(payload).encode())>32768:raise ValueError('Native frame payload exceeds bound')
    return payload,variants(source,unit),variants(target,unit)


def export_pair(rows,source,target,output,revision,key,key_id,source_manifest):
    output.mkdir(parents=True,exist_ok=False);database=output/'frames.sqlite';counts={}
    with sqlite3.connect(database) as db:
        db.executescript(SCHEMA)
        for row in rows:
            payload,left,right=compile_record(row)
            if (payload['source_language'],payload['target_language'])!=(source,target):raise ValueError('Wrong pair')
            db.execute('INSERT INTO mappings VALUES (?,?,?)',(payload['id'],canonical(payload),canonical(row)))
            for side,values in [('source',left),('target',right)]:
                db.executemany('INSERT INTO '+side+'_inputs VALUES (?,?)',[(value,payload['id']) for value in values])
        for side in ('source','target'):
            if db.execute('SELECT count(*) FROM (SELECT input FROM '+side+'_inputs GROUP BY input HAVING count(*)>256)').fetchone()[0]:
                raise ValueError('Frame shortlist exceeds bound')
            counts[side+'_variants']=db.execute('SELECT count(*) FROM '+side+'_inputs').fetchone()[0]
        metadata={'schema':'vipi-reviewed-frame-2','pack_id':source+'-'+target,'source_language':source,
            'target_language':target,'context_policy':POLICY}
        db.executemany('INSERT INTO metadata VALUES (?,?)',metadata.items());db.commit();db.execute('VACUUM')
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Invalid frame database')
    if not 512<=database.stat().st_size<=67108864:raise ValueError('Frame pack size bound exceeded')
    manifest=dict(metadata,schema_version=7,revision=revision,normalization='exact-utf16',file='frames.sqlite',
        bytes=database.stat().st_size,sha256=digest_file(database),mappings=len(rows),**counts,
        export_sha256=source_manifest['records_sha256'],through_sequence=source_manifest['through_sequence'],
        key_id=key_id,signature_algorithm='ECDSA-P256-SHA256',compiler_sha256=digest_file(Path(__file__)),
        release_ready=False,quality='explicitly-assessed-development-phrase-frames')
    encoded=canonical(manifest).encode();signature=key.sign(encoded,ec.ECDSA(hashes.SHA256()))
    key.public_key().verify(signature,encoded,ec.ECDSA(hashes.SHA256()))
    (output/'manifest.json').write_bytes(encoded);(output/'manifest.sig').write_bytes(signature)
    (output/'ATTRIBUTION.txt').write_text('Exact provenance, phrase-scope assessments and limits are retained in mappings.evidence.\n'
        'Changes: explicitly enumerated source and target phrase indexes. Qualification, not release acceptance.\n')
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--revision',type=int,required=True);p.add_argument('--key-id',required=True);a=p.parse_args()
    if a.revision<1:raise ValueError('Positive revision required')
    manifest,rows=load_export(a.input);a.output.mkdir(parents=True,exist_ok=False)
    key=ec.generate_private_key(ec.SECP256R1())
    (a.output/'signing-public-key.der').write_bytes(key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo))
    pairs={}
    for row in rows:
        record=row['record'];pairs.setdefault((record['source_language'],record['target_language']),[]).append(row)
    results=[export_pair(values,s,t,a.output/(s+'-'+t),a.revision,key,a.key_id,manifest) for (s,t),values in sorted(pairs.items())]
    receipt={'schema':'vipi-reviewed-frame-build-1','qualification_only_key':True,'private_key_written':False,
        'release_ready':False,'records':len(rows),'pairs':results,'bytes':sum(r['bytes'] for r in results),
        'export_sha256':manifest['records_sha256'],'compiler_sha256':digest_file(Path(__file__))}
    (a.output/'receipt.json').write_text(canonical(receipt)+'\n')
    print(canonical({k:v for k,v in receipt.items() if k!='pairs'}|{'pairs':len(results)}))
