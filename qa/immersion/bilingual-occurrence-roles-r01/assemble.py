import hashlib,json
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-bilingual-occurrence-roles-20261109-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
s=json.loads((W/'selection-freeze.json').read_text());align=json.loads((W/'control-alignment.json').read_text());cases=[]
for n,c in enumerate(s['cases'],1):
 p=c['pair']
 if 'forward_links' not in p:
  for side in ('forward','reverse'):
   assert p['index']==align[side]['pair_index'];p[side+'_links']=[list(map(int,t.split('-'))) for t in align[side]['line'].split()]
 union={tuple(t) for t in p['forward_links']+p['reverse_links']}
 for a,b in union:assert 0<=a<len(p['source']['tokens']) and 0<=b<len(p['target']['tokens'])
 focuses=[]
 for o in c['retained_occurrences']:
  a,b=o['source_tokens'];key=(tuple(range(a,b)),tuple(o['aligned_target_tokens']))
  if not any((tuple(x['source_indices']),tuple(x['target_indices']))==key for x in focuses):focuses.append({'source_indices':list(key[0]),'target_indices':list(key[1]),'provenance':'retained_candidate_occurrence','head_ids':[]})
  next(x for x in focuses if (tuple(x['source_indices']),tuple(x['target_indices']))==key)['head_ids'].append(o['head_id'])
 for a in c['extra_source_tokens']:
  targets=sorted(b for x,b in union if x==a)
  if not any(x['source_indices']==[a] and x['target_indices']==targets for x in focuses):focuses.append({'source_indices':[a],'target_indices':targets,'provenance':'explicit_development_control','head_ids':[]})
 for x in focuses:x['head_ids']=sorted(set(x['head_ids']))
 cases.append({'case_id':f'{n:03d}','stratum':c['stratum'],'control':c.get('control'),'pair_id':c['pair_id'],'pair':p,'focuses':focuses,'source_focus_indices':sorted({i for x in focuses for i in x['source_indices']}),'target_focus_indices':sorted({i for x in focuses for i in x['target_indices']})})
result={'schema':'bilingual-supplied-token-role-packet-r01','selection_sha256':sha(W/'selection-freeze.json'),'control_alignment_sha256':sha(W/'control-alignment.json'),'model_outputs_seen':False,'review_scope':'Independently label every indexed focus token on both sides from full sentence. Preserve per-focus compound and unassessable flags. No gold or population claim.','cases':cases}
p=W/'packet.json'
with p.open('x') as f:json.dump(result,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n')
print(sha(p),p.stat().st_size)
for c in cases:print(c['case_id'],c['stratum'],c['pair']['source']['text'],'|||',c['pair']['target']['text'],'FOCUS',[(i,c['pair']['source']['tokens'][i]['text']) for i in c['source_focus_indices']],[(i,c['pair']['target']['tokens'][i]['text']) for i in c['target_focus_indices']])
