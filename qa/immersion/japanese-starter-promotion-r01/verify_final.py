#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,collections
W=Path('/home/ai/Development/investigations/vipi-japanese-starter-promotion-20261109-r01')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def view(row,reading):
 raw=row['original'].encode('utf-16-le')
 for s in sorted(row['spans'],key=lambda x:x['source_utf16'][0],reverse=True):
  a,b=s['source_utf16'];assert raw[a*2:b*2].decode('utf-16-le')==s['source'];face=(s.get('reading') if reading else None) or s['target'];raw=raw[:a*2]+face.encode('utf-16-le')+raw[b*2:]
 return raw.decode('utf-16-le')
def main():
 paths={'apple_previous':W/'apple-output-r01.json','android_previous':W/'android-capture-r04/output.stdout','apple_final':W/'apple-output-r05.json','android_final':W/'android-capture-r06/output.stdout'}
 data={k:json.loads(p.read_text()) for k,p in paths.items()};tables={k:{(x['id'],x['known_state']):x for x in d['cases']} for k,d in data.items()};assert all(len(t)==384 for t in tables.values())
 out={'schema':1,'bindings':{k:{'path':str(p),'sha256':sha(p)} for k,p in paths.items()},'platforms':{},'all384_final_span_arrays_equal':True,'source_provider_injection_used':False}
 for platform in ['apple','android']:
  new=data[platform+'_final'];assert new['activation'] and new['default_provider_path'];deltas=[];prior=tables[platform+'_previous'];final=tables[platform+'_final'];assert final.keys()==prior.keys()
  for key,b in final.items():
   a=prior[key];assert a['original']==b['original'] and a['known_ids']==b['known_ids'];assert b['translation_calls']==0 and b['status'].lower()!='stale'
   assert b['spans']==tables['apple_final'][key]['spans']
   if b['spans']!=a['spans']:
    assert key[0]=='ja-fresh-011' and key[1] in [0,1];assert len(a['spans'])==1 and a['spans'][0]['source']=='Winter' and not b['spans']
    deltas.append({'id':key[0],'known_state':key[1],'source':b['original'],'before':a['spans'],'after':b['spans']})
   assert view(b,platform=='android')==b['mixed']
  assert len(deltas)==2
  out['platforms'][platform]={'nonempty_by_known_state':[sum(bool(x['spans']) for x in final.values() if x['known_state']==s) for s in range(3)],'only_changes':deltas,'translation_calls':0,'unchanged_span_arrays':382,'default_identity':new.get('default_provider_identity'),'empty_not_semantic_success':True}
 p=W/'final-verification-r06.json';assert not p.exists();p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'sha256':sha(p),'path':str(p),'complete':True}))
if __name__=='__main__':main()
