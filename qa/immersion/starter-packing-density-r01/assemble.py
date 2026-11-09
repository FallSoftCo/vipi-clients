#!/usr/bin/env python3
"""Read-only compact density qualification join; no selection or label changes."""
import json,hashlib,collections
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-starter-packing-density-20261109-r01')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def unit(s):return (tuple(s['source_utf16']),s['source'],s['target'],s['reading'])
def utf(s,a,b):return s.encode('utf-16-le')[a*2:b*2].decode('utf-16-le')
def main():
 out=W/'review-r01';assert not out.exists();out.mkdir()
 receipt=json.loads((W/'android-capture-r01/receipt.json').read_text());assert receipt['success']
 raw=W/'android-capture-r01/output.stdout';assert digest(raw)==receipt['output_sha256']
 status=json.loads((W/'android-capture-r01/status.stdout').read_text());assert status['complete'] and status['parity_025']==768
 labels={x['bits']:x['labels'] for x in status['density_records']}
 old=json.loads((W/'inputs/packing-reference.json').read_text())['cases'];seen=collections.defaultdict(set)
 for r in old:seen[r['pair'],r['id']].update(unit(s) for s in r['b_direct'])
 rows=[json.loads(l) for l in raw.open()];assert len(rows)==768
 groups={};metrics=collections.defaultdict(lambda:collections.Counter());novel=set();state_novel=set();precision=[]
 for r in rows:
  key=(r['pair'],r['id']);g=groups.setdefault(key,{'pair':key[0],'id':key[1],'source':r['source'],'stratum':r['stratum'],'options':{}})
  assert g['source']==r['source'];bylabel={}
  for step in r['steps']:
   o=r['outputs'][step['output']];e=r['evidence'][step['evidence']];sp=o['spans'];refs=o['references'];assert len(sp)==len(refs)
   cost=0;end=-1
   for s,ref in zip(sp,refs):
    a,b=s['source_utf16'];assert a>=end and utf(r['source'],a,b)==s['source'];end=b
    assert ref['scope']==[a,b]
    touched=[x for x in r['native_words'] if x[0]<b and a<x[1]]
    assert touched and touched[0][0]==a and touched[-1][1]==b and all(a<=x[0] and x[1]<=b for x in touched)
    assert len(touched)==ref['native_cost'];cost+=len(touched)
    assert any(t['reason'] is None and t['source_utf16']==[a,b] and t['target']==s['target'] and t['reading']==s['reading'] for t in e['trace'])
    if unit(s) not in seen[key]:novel.add((key,unit(s)));state_novel.add((key,r['known_state'],unit(s)))
   assert cost<=step['budget']
   if sp:
    oid=hashlib.sha256(json.dumps({'spans':sp,'mixed':o['mixed']},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    option=g['options'].setdefault(oid,{'variant_id':oid,'mixed':o['mixed'],'spans':sp,'novel_spans':[s for s in sp if unit(s) not in seen[key]],'occurs_at':[]})
    option['occurs_at'].append({'state':r['known_state'],'density_labels':labels[step['density_bits']]})
   for label in labels[step['density_bits']]:
    bylabel[label]=step['output'];m=metrics[(r['pair'],r['known_state'],label)];m.update(cases=1,native_words=len(r['native_words']),nonempty=int(bool(sp)),emitted_words=cost,units=len(sp))
  for n in range(16):
   if bylabel['canonical-double-'+str(n)]!=bylabel['android-slider-'+str(n)]:precision.append({'pair':key[0],'id':key[1],'state':r['known_state'],'step':n})
 packet=[]
 for key,g in sorted(groups.items()):
  g['options']=sorted(g['options'].values(),key=lambda x:x['variant_id'])
  if any(o['novel_spans'] for o in g['options']):packet.append(g)
 allg=[dict(g) for key,g in sorted(groups.items())]
 result={'input_sha256':digest(raw),'all_cases':768,'unique_source_pair_groups':len(groups),'novel_occurrences':len(novel),'state_specific_novel_occurrences':len(state_novel),'review_groups':len(packet),'review_options':sum(len(g['options']) for g in packet),'precision_differences':precision,'metrics':[dict(pair=k[0],state=k[1],density=k[2],**v) for k,v in sorted(metrics.items())],'empty_not_quality':True,'activated':False}
 for name,value in [('anonymous-packet.json',packet),('all-unique-outputs.json',allg),('metrics.json',result)]:
  (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
 (out/'receipt.json').write_text(json.dumps({'script_sha256':digest(Path(__file__)),'raw_sha256':digest(raw),'prior_sha256':digest(W/'inputs/packing-reference.json'),'files':{p.name:{'sha256':digest(p),'bytes':p.stat().st_size} for p in out.iterdir()}},indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k not in ('metrics','precision_differences')}))
if __name__=='__main__':main()
