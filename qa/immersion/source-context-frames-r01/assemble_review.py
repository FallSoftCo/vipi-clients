#!/usr/bin/env python3
"""Package frozen native outputs without exposing methods or parallel witnesses in review."""
import argparse,json,hashlib
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01')
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def digest(x):return hashlib.sha256(enc(x)).hexdigest()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def mixed(source,spans,reading):
 b=source.encode('utf-16-le')
 for s in sorted(spans,key=lambda x:x['source_utf16'][0],reverse=True):
  a,z=s['source_utf16'];assert b[a*2:z*2].decode('utf-16-le')==s['source']
  b=b[:a*2]+((s.get('reading') or s['target']) if reading else s['target']).encode('utf-16-le')+b[z*2:]
 return b.decode('utf-16-le')
def main():
 p=argparse.ArgumentParser();p.add_argument('--android',type=Path);p.add_argument('--apple',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();assert not a.out.exists()
 sources=json.loads((W/'native-inputs-r02/cases.json').read_text())['cases'];expected={(c['pair'],c['id']):c for c in sources};groups={};bindings={};counts={}
 for platform,path in [('android',a.android),('apple',a.apple)]:
  if path is None:continue
  rows=[json.loads(l) for l in path.read_text().splitlines() if l.strip()];assert len(rows)==656;seen=set();counts[platform]=len(rows)
  for r in rows:
   c=expected[r['pair'],r['id']];assert r['source']==c['source'];key=(r['pair'],r['id'],r['state'],r['density']);assert key not in seen;seen.add(key)
   group=groups.setdefault((r['pair'],r['source']),{'pair':r['pair'],'source':r['source'],'source_ids':set(),'exposure':set(),'options':{}});group['source_ids'].add(r['id']);group['exposure'].add(c['exposure'])
   for arm in ['baseline','candidate']:
    for layer in ['direct','route']:
     spans=r[arm]['spans'] if layer=='direct' else r['route'][arm]['spans']
     canonical=[{k:s.get(k) for k in ['source','target','reading','source_utf16']} for s in spans]
     value={'spans':canonical,'mixed_reading':mixed(r['source'],canonical,True),'mixed_script':mixed(r['source'],canonical,False),'zero_immersion':not canonical}
     if layer=='route':assert value['mixed_reading']==r['route'][arm]['mixed']
     h=digest(value);group['options'][h]=value
     bind={'platform':platform,'source_id':r['id'],'pair':r['pair'],'state':r['state'],'density':r['density'],'arm':arm,'layer':layer}
     bindings.setdefault((r['pair'],r['source'],h),[]).append(bind)
 packet=[];key=[]
 for i,(gk,g) in enumerate(sorted(groups.items()),1):
  cid=f'frame-review-{i:03d}';options=[]
  for j,h in enumerate(sorted(g['options'],key=lambda h:digest(['anonymous-option-v1',gk,h])),1):
   oid=f'{cid}-option-{h[:12]}';b=bindings[gk[0],gk[1],h];options.append({'option_id':oid,**g['options'][h],'occurrence_count':len(b)});key.append({'case_id':cid,'option_id':oid,'bindings':b})
  packet.append({'case_id':cid,'pair':g['pair'],'source':g['source'],'source_ids':sorted(g['source_ids']),'exposure':sorted(g['exposure']),'options':options})
 a.out.mkdir();files={'anonymous-review.json':{'schema':'vipi-frame-anonymous-review-1','review_kind':'Independent agent diagnostic review; no population or native-speaker claim','prior_seed_pattern_exposure':True,'cases':packet},'method-key.json':key,'witnesses.json':{'source_cases':sources,'proofs_path':str(W/'preparation-r01/proofs.json'),'proofs_sha256':sha(W/'preparation-r01/proofs.json')}}
 for name,value in files.items():(a.out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
 receipt={'inputs':{str(x):sha(x) for x in [a.android,a.apple] if x is not None},'script_sha256':sha(Path(__file__)),'rows':counts,'cases':len(packet),'options':sum(len(c['options']) for c in packet),'files':{n:sha(a.out/n) for n in files},'labels_seen':False}
 (a.out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
