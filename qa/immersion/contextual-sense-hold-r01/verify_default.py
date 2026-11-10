#!/usr/bin/env python3
from pathlib import Path
import json,hashlib
W=Path('/home/ai/Development/investigations/vipi-contextual-sense-hold-20261109-r01');P=Path('/home/ai/Development/investigations/vipi-conversation-depth-20261109-r01');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'android-default-verification-r01.json';assert not out.exists()
 old=P/'android-capture-r01/output.stdout';new=W/'android-capture-r01/output.stdout';key=lambda x:(x['id'],x['pair'],x['density'])
 a={key(x):x for x in map(json.loads,old.read_text().splitlines())};b={key(x):x for x in map(json.loads,new.read_text().splitlines())};assert a.keys()==b.keys() and len(a)==320
 changed=[]
 for k,x in a.items():
  y=b[k];assert y['translation_calls']==0 and y['error_class'] is None
  for field in ['source','stratum','native_words','known_ids','actual_default_factory','provider_target_spans_injected','reference_hit']:assert x[field]==y[field],(k,field)
  removed=[s for s in x['spans'] if k[1]=='en-sw' and x['source']=="He's one of the ones without hair!" and s['source']=='hair' and s['target']=='nywele']
  assert y['spans']==[s for s in x['spans']if s not in removed],k
  for field,target in [('mixed_script','target'),('mixed_reading','reading')]:
   raw=y['source'].encode('utf-16-le')
   for s in reversed(y['spans']):
    start,end=s['source_utf16'];raw=raw[:start*2]+(s.get(target)or s['target']).encode('utf-16-le')+raw[end*2:]
   assert raw.decode('utf-16-le')==y[field]
   if not removed:assert x[field]==y[field]
  if removed:
   for s in removed:
    start,end=s['source_utf16'];recognitions=y['source_evidence']['recognitions']
    assert any(n['mask'] and n['mask'][0]<=start and n['mask'][1]>=end and not n['approved']for n in recognitions)
   changed.append({'id':k[0],'pair':k[1],'density':k[2],'source':x['source'],'before_spans':x['spans'],'after_spans':y['spans'],'before_script':x['mixed_script'],'after_script':y['mixed_script'],'removed':removed})
 assert len(changed)==2
 r=W/'android-capture-r01';receipt=json.loads((r/'receipt.json').read_text());assert not receipt['success'] and receipt['closure']['main_unchanged'];status=json.loads((r/'status.stdout').read_text());assert status['rows']==320 and status['captured_exceptions']==0
 for prefix in ['settings','system']:assert(r/(prefix+'-before.stdout')).read_bytes()==(r/(prefix+'-after.stdout')).read_bytes()
 controls={'qualified':False,'failure':'Existing legacy catalog emitted no unmasked hair span; positive prerequisite failed after complete default capture.'}
 paths=[old,new,r/'receipt.json',r/'capture.stdout',W/'protocol.json',W/'android-freeze-r01.json',Path(__file__)]
 out.write_text(json.dumps({'rows':320,'unchanged_selected_outputs':318,'changed':changed,'calls':0,'constructed_target_control':controls,'closure':receipt['closure'],'settings_unchanged':True,'coverage_claim':'Withholding only; valid human hair is also deliberately omitted. No alternative translation or inference.','bindings':{str(p):sha(p)for p in paths}},ensure_ascii=False,indent=2)+'\n');print('verified',sha(out))
if __name__=='__main__':main()
