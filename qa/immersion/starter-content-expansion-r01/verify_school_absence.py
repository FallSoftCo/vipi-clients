#!/usr/bin/env python3
"""Read all retained inputs and native traces; do not rerun selection."""
import json,hashlib
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-starter-content-expansion-20261109-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 inp=W/'native-inputs-r03/comparison-inputs.json';data=json.loads(inp.read_text());input_hits=[{'pair':p,'id':c['id']} for p,cs in data['pairs'].items() for c in cs if 'schools' in c['source'].casefold()]
 raw=W/'android-capture-r02/output.stdout';rows=0;trace_rows=0;hits=[]
 for line in raw.open():
  r=json.loads(line);rows+=1
  for hash,e in r['evidence'].items():
   for t in e['trace']:
    trace_rows+=1
    if t['entry_id'] in ['word-en-ja-schools','word-en-sw-schools']:hits.append({'pair':r['pair'],'id':r['id'],'state':r['state'],'evidence_hash':hash,'trace':t})
 assert rows==1386 and not hits and not input_hits
 checks={}
 for lang,old,new in [('ja','004','005'),('sw','003','004')]:
  a=W/'candidates-r02'/f'starter-en-{lang}-{old}.json';b=W/'candidates-r03'/f'starter-en-{lang}-{new}.json';x=json.loads(a.read_text());y=json.loads(b.read_text());id=f'word-en-{lang}-schools';assert y['entries']==[e for e in x['entries'] if e['id']!=id];assert x['source_context_sets']==y['source_context_sets'];checks[lang]={'parent_sha256':sha(a),'successor_sha256':sha(b),'sole_entry_delta':id,'retained_entry_objects_and_order_identical':True,'matching_source_tokens':['schools']}
 result={'schema':1,'code_sha256':sha(Path(__file__)),'input_sha256':sha(inp),'android_output_sha256':sha(raw),'source_pair_rows':sum(map(len,data['pairs'].values())),'native_source_state_rows':rows,'trace_records_scanned':trace_rows,'literal_substring_input_hits':input_hits,'native_recognition_hits':hits,'successor_checks':checks,'conclusion':'No plural schools input or actual Android trace recognition. Removing only that never-matched record preserves the recorded selection inputs/order; pack/cache/reference identities change. Final new-bundle/default-route qualification is still required; no extra full grid executed.','activation':False}
 p=W/'schools-recognition-census-r01.json';assert not p.exists();p.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n');print(json.dumps({'receipt_sha256':sha(p),'rows':rows,'trace_records_scanned':trace_rows,'hits':len(hits)}))
if __name__=='__main__':main()
