#!/usr/bin/env python3
"""Read-only independent output reconciliation; no selector imports or executions."""
from pathlib import Path
import json,hashlib
W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'android-production-verification-r01.json';assert not out.exists()
 old=W/'android-capture-r03/output.stdout';new=W/'android-production-capture-r01/output.stdout'
 a=[json.loads(x) for x in old.read_text().splitlines()];b=[json.loads(x) for x in new.read_text().splitlines()];assert len(a)==len(b)==656
 corrections={'frame-4dc1128ff5c7283136d7125c':'sherehe','frame-43431e9665d734366a927b81':'nambari ya simu'};changes=[]
 for previous,actual in zip(a,b):
  for k in ['id','pair','source','state','density']:assert previous[k]==actual[k],k
  expected=json.loads(json.dumps(previous['route']['candidate']['spans']))
  if previous['pair']=='en-sw' and previous['routing_branch']=='reference_miss_frame_evidence':
   for span in expected:
    for r in previous['candidate']['references']:
     if r['scope']==span['source_utf16']:
      for identifier,target in corrections.items():
       if r['reference'].endswith(':'+identifier):span['target']=target;changes.append({'id':previous['id'],'state':previous['state'],'density':previous['density'],'scope':span['source_utf16'],'target':target})
  assert actual['spans']==expected,(previous['id'],previous['pair'])
  assert actual['origin']==previous['route']['candidate'].get('origin') and actual['translation_calls']==0
  # Projection is UTF16-aware and uses reading where available, as native mixed view.
  encoded=actual['source'].encode('utf-16-le');parts=[];end=0
  for s in expected:
   start,stop=s['source_utf16'];assert start>=end and encoded[start*2:stop*2].decode('utf-16-le')==s['source']
   parts.extend([encoded[end*2:start*2].decode('utf-16-le'),s['reading'] or s['target']]);end=stop
  parts.append(encoded[end*2:].decode('utf-16-le'));assert actual['mixed']==''.join(parts)
 assert len(changes)==8
 receipt=W/'android-production-capture-r01/receipt.json';r=json.loads(receipt.read_text());assert r['success'] and r['closure']['main_unchanged'] and r['closure']['owned_emulator_exit']==0
 p=receipt.parent;assert (p/'settings-before.stdout').read_bytes()==(p/'settings-after.stdout').read_bytes()
 out.write_text(json.dumps({'rows':656,'only_expected_corrected_spans':changes,'all_other_spans_and_origins_equal':True,'complete_mixed_outputs_reconstructed':True,'translation_calls':0,'settings_identical':True,'bindings':{str(p):sha(p) for p in [old,new,receipt,Path(__file__)]}},indent=2)+'\n');print(sha(out))
if __name__=='__main__':main()
