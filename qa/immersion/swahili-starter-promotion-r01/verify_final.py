#!/usr/bin/env python3
"""Exact cross-native parity and known-state amendment delta; no semantic relabeling."""
from pathlib import Path
import argparse,json,hashlib,collections
p=argparse.ArgumentParser();p.add_argument('work',type=Path);a=p.parse_args();w=a.work
paths={'apple_candidate':w/'apple-output-r01.json','android_candidate':w/'android-capture-r01/output.stdout','apple_final':w/'apple-output-r02.json','android_final':w/'android-capture-r02/output.stdout'}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();values={k:json.loads(p.read_text()) for k,p in paths.items()}
key=lambda r:(r['id'],r['known_state'])
for name,d in values.items():
 assert d['complete'] and len(d['cases'])==384 and d['japanese_parity_rows']==384
 assert all(r['translation_calls']==0 and r['status'].lower()!='stale' for r in d['cases'])
 assert len({key(r) for r in d['cases']})==384
 assert all(s['reading'] is None for r in d['cases'] for s in r['spans'])
 assert d['activation']==('final' in name) and d['default_provider_path']==('final' in name)
for stage in ['candidate','final']:
 apple={key(r):r for r in values['apple_'+stage]['cases']};android={key(r):r for r in values['android_'+stage]['cases']}
 assert apple.keys()==android.keys()
 for k,r in apple.items():assert r['spans']==android[k]['spans'],(stage,k)
old={key(r):r for r in values['apple_candidate']['cases']};new={key(r):r for r in values['apple_final']['cases']};deltas=[]
for k,r in new.items():
 before=old[k];assert before['original']==r['original']
 if before['spans']!=r['spans']:
  assert r['known_state']==1
  assert any(s['source'].lower() in ['family','families'] for s in before['spans'])
  deltas.append({'id':r['id'],'known_state':1,'original':r['original'],'before_mixed':before['mixed'],'after_mixed':r['mixed'],'removed':[s for s in before['spans'] if s not in r['spans']],'added':[s for s in r['spans'] if s not in before['spans']]})
summary={}
for stage in ['candidate','final']:
 rows=values['apple_'+stage]['cases'];summary[stage]={str(s):{'messages':128,'nonempty':sum(bool(r['spans']) for r in rows if r['known_state']==s),'emissions':sum(len(r['spans']) for r in rows if r['known_state']==s)} for s in range(3)}
out={'complete':True,'bindings':{k:{'path':str(p),'sha256':sha(p)} for k,p in paths.items()},'cross_native_exact_rows_each_revision':384,'ja_unchanged_rows_each_platform_revision':384,'sw_readings_absent':True,'known_state_correction':'family→families; no content change','metrics':summary,'deltas':deltas,'semantic_review_required_for_added':True,'no_population_coverage_claim':True}
f=w/'final-verification-r02.json';assert not f.exists();f.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(sha(f),json.dumps(summary),len(deltas))
