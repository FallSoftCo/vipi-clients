#!/usr/bin/env python3
"""Capture only changed QA inputs; retain explicit provenance for reused outputs."""
import argparse
import json
from pathlib import Path
from conversation_corpus import sha_file,write_json

METHOD=('schema','window_extents','maximum_phrase_characters','maximum_window_words')


def identity(row):return row['case'],row['source'],row['target']


def indexed(rows):
    result={identity(r):r for r in rows}
    if len(result)!=len(rows):raise ValueError('Duplicate directed case')
    return result


def changed(base,full):
    if any(base[k]!=full[k] for k in METHOD):raise ValueError('Changed translation sampling method requires a new full capture')
    old=indexed(base['samples']);indexed(full['samples'])
    return [r for r in full['samples'] if old.get(identity(r))!=r]


def checked_capture(protocol,capture,digest):
    expected=indexed(protocol['samples']);actual=indexed(capture['results'])
    if not capture.get('complete') or capture.get('protocol_sha256')!=digest:raise ValueError('Incomplete or wrong capture')
    if actual.keys()!=expected.keys() or capture['cases_expected']!=len(actual) or capture['cases_completed']!=len(actual):raise ValueError('Wrong captured cases')
    for k,row in actual.items():
        if row.get('status')!='executed' or not isinstance(row.get('translation'),str) or not row['translation'].strip():raise ValueError('Failed translation')
        if any(row.get(field)!=value for field,value in expected[k].items()):raise ValueError('Capture changed a requested input')
    return actual


def combine(base,full,delta,old_capture,new_capture,hashes):
    required=indexed(changed(base,full))
    if indexed(delta['samples'])!=required or any(delta[k]!=full[k] for k in METHOD):raise ValueError('Delta does not equal changed inputs')
    old=checked_capture(base,old_capture,hashes['base_protocol'])
    new=checked_capture(delta,new_capture,hashes['delta_protocol'])
    if old_capture['provider']!=new_capture['provider']:raise ValueError('Different provider labels')
    rows=[]
    for sample in full['samples']:
        k=identity(sample);fresh=k in required
        rows.append(dict(new[k] if fresh else old[k],capture_provenance_sha256=hashes['delta_capture' if fresh else 'base_capture']))
    return {'schema':'vipi-local-phrase-observations-1','protocol_sha256':hashes['full_protocol'],
        'provider':old_capture['provider'],'complete':True,'cases_expected':len(rows),'cases_completed':len(rows),
        'network_absence_verified':old_capture['network_absence_verified'] and new_capture['network_absence_verified'],
        'composite_capture':True,'reused_cases':len(rows)-len(new),'delta_cases':len(new),
        'fresh_calls_in_delta':new_capture.get('fresh_calls_this_run'),
        'component_sha256':hashes,'model_identity_limit':'Retained provider outputs from separate QA runs; identical model contents are not asserted.',
        'linguistic_acceptance':False,'runtime_integration':False,'results':rows}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['plan','combine'])
    for name in ('base-protocol','full-protocol','output'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('delta-protocol','base-capture','delta-capture'):p.add_argument('--'+name,type=Path)
    p.add_argument('--apple-run-id');a=p.parse_args()
    if a.output.exists():raise ValueError('Preserve previous result')
    base=json.loads(a.base_protocol.read_text());full=json.loads(a.full_protocol.read_text())
    if a.mode=='plan':
        if not a.apple_run_id or not a.apple_run_id.isascii() or not a.apple_run_id.isdigit() or len(a.apple_run_id)!=3:raise ValueError('Three-digit run ID required')
        rows=changed(base,full)
        if not rows:raise ValueError('No new capture required')
        result=dict(full,qa_run_id=a.apple_run_id,samples=rows,
            incremental_provenance={'base_protocol_sha256':sha_file(a.base_protocol),'full_protocol_sha256':sha_file(a.full_protocol),
                'reused_cases':len(full['samples'])-len(rows),'changed_cases':len(rows)})
    else:
        if not all((a.delta_protocol,a.base_capture,a.delta_capture)):raise ValueError('All component paths required')
        paths={k:getattr(a,k) for k in ('base_protocol','full_protocol','delta_protocol','base_capture','delta_capture')}
        result=combine(base,full,json.loads(a.delta_protocol.read_text()),json.loads(a.base_capture.read_text()),json.loads(a.delta_capture.read_text()),{k:sha_file(v) for k,v in paths.items()})
    write_json(a.output,result)
    print(json.dumps({'output':str(a.output),'sha256':sha_file(a.output),
        'cases':len(result.get('samples',result.get('results',[]))),'composite':result.get('composite_capture',False)}))
