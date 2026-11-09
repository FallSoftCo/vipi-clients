#!/usr/bin/env python3
"""Lossless anonymous full-output review; method bindings stay in a separate file."""
import hashlib,json,sys
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-starter-content-expansion-20261109-r01')
def enc(x):return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def digest(x):return hashlib.sha256(x).hexdigest()
def main():
 raw=W/'android-capture-r01/output.stdout';apple=Path(sys.argv[1]);status=json.loads((W/'android-capture-r01/status.stdout').read_text());assert status['complete']
 out=W/'review-r01';assert not out.exists();out.mkdir()
 inputs=json.loads((W/'inputs-r02/comparison-inputs.json').read_text());source={(p,c['id']):c for p,cs in inputs['pairs'].items() for c in cs}
 witnesses={(x['pair'],x['id']):x for x in json.loads((W/'inputs-r02/source-witnesses.json').read_text())}
 groups={};links=[];rows=0
 for platform,path in [('android',raw),('apple',apple)]:
  count=0
  for line in path.open():
   if not line.strip():continue
   r=json.loads(line);rows+=1;count+=1;k=(r['pair'],r['id']);g=groups.setdefault(k,{})
   assert r['source']==source[k]['source']
   for step in r['steps']:
    for arm,b in step['arms'].items():
     result=r['outputs'][b['output']]
     for route in ['direct','route']:
      option={'mixed':result[route+'_mixed'],'spans':result[route+'_spans']};h=digest(enc(option));g[h]=option
      links.append({'platform':platform,'pair':k[0],'id':k[1],'state':r['state'],'density_bits':step['density_bits'],'arm':arm,'route':route,'option_hash':h,'output_hash':b['output'],'evidence_hash':b['evidence']})
  assert count==1386
 assert rows==2772 and len(groups)==462
 cases=[];labels={}
 for k,options in sorted(groups.items()):
  # Stable salted order; no ranking by output quality or treatment.
  ordered=sorted(options,key=lambda h:digest(('starter-content-review-r01/'+str(k)+'/'+h).encode()))
  display=[]
  for i,h in enumerate(ordered):
   label='option-'+str(i+1).zfill(2);labels[k+(h,)]=label;display.append({'label':label,**options[h],'zero_immersion':not options[h]['spans']})
  cases.append({'pair':k[0],'id':k[1],'source':source[k]['source'],'stratum':source[k]['stratum'],'historically_exposed':source[k]['historically_exposed'],'preceding_source_context':witnesses.get(k,{}).get('preceding_source_context',[]),'options':display})
 for link in links:link['label']=labels[link['pair'],link['id'],link.pop('option_hash')]
 packet={'schema':1,'review_kind':'independent agent; no semantic gold','cases':cases,'scope':'All distinct direct and normal-route outputs; exact repeated options propagate only within the same source/pair. Empty options have zero usefulness.'}
 (out/'anonymous-packet.json').write_bytes(enc(packet));(out/'method-key.json').write_bytes(enc(links))
 receipt={'input_sha256':{'android':digest(raw.read_bytes()),'apple':digest(apple.read_bytes())},'assembler_sha256':digest(Path(__file__).read_bytes()),'packet_sha256':digest((out/'anonymous-packet.json').read_bytes()),'key_sha256':digest((out/'method-key.json').read_bytes()),'rows':rows,'cases':len(cases),'options':sum(len(c['options']) for c in cases),'all_predictions_bound':len(links),'meaning_labels_created':False}
 (out/'receipt.json').write_bytes(enc(receipt));print(json.dumps(receipt))
if __name__=='__main__':main()
