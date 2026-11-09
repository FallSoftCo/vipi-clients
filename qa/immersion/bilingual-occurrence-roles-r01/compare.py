import collections,hashlib,json
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-bilingual-occurrence-roles-20261109-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def enc(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def key(e):return hashlib.sha256(json.dumps([e['language'],e['id'],e['text'],e['tokens']],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
p=json.loads((W/'packet.json').read_text());a=json.loads((W/'author-review-r01.json').read_text());r=json.loads((W/'root-review-r01.json').read_text());receipt=json.loads((W/'outputs-r02/receipt.json').read_text());assert receipt['complete'];assert sha(W/'outputs-r02/annotations.jsonl')==receipt['outputs']['annotations.jsonl']['sha256'];models={x['endpoint_key']:x for x in map(json.loads,(W/'outputs-r02/annotations.jsonl').read_text().splitlines())};assert len(models)==64
assert sha(W/'author-review-r01.json')=='b3b5a9675e6610bf459515488c03ef733d630b06017a1064540ed89a033f55c1';assert sha(W/'root-review-r01.json')=='a196b888aa1468e240fb65ad18c3fb3796cf834316e8e36a6e2df234a30da61d'
for review in (a,r):assert review['packet_sha256']==sha(W/'packet.json') and not review['model_output_seen'] and not review['other_reviewer_labels_seen'];assert len(review['cases'])==32
counts=collections.defaultdict(collections.Counter);focuscounts=collections.defaultdict(collections.Counter);cases=[];disagreements=[];errors=[]
for c,ar,rr in zip(p['cases'],a['cases'],r['cases']):
 assert c['case_id']==ar['case_id']==rr['case_id'];out={'case_id':c['case_id'],'stratum':c['stratum'],'pair_id':c['pair_id'],'source':[],'target':[],'focus_flags':{'author':ar['focus_flags'],'root':rr['focus_flags']}}
 for side in ('source','target'):
  model=models[key(c['pair'][side])];assert model['text_sha256']==hashlib.sha256(c['pair'][side]['text'].encode()).hexdigest()
  assert [x['index'] for x in ar[side]]==[x['index'] for x in rr[side]]==c[side+'_focus_indices']
  for au,ro in zip(ar[side],rr[side]):
   i=au['index'];assert au['text']==ro['text']==c['pair'][side]['tokens'][i]['text'];prediction=model['tokens'][i];assert prediction[:2]==c['pair'][side]['tokens'][i]['utf16'];entry={'index':i,'text':au['text'],'author':au,'root':ro,'model_role':prediction[2],'model_score':prediction[3]};out[side].append(entry)
   if au['role']!=ro['role']:disagreements.append({'case_id':c['case_id'],'side':side,'entry':entry})
   for reviewer,ref in [('author',au),('root',ro)]:
    metric=counts[(reviewer,c['stratum'],side)];metric['tokens']+=1;metric['role_matches']+=prediction[2]==ref['role'];metric['reference_nouns']+=ref['role']=='NOUN';metric['false_noun_rejections']+=ref['role']=='NOUN' and prediction[2]!='NOUN';metric['false_noun_acceptances']+=ref['role']!='NOUN' and prediction[2]=='NOUN'
    if prediction[2]!=ref['role']:errors.append({'reviewer':reviewer,'case_id':c['case_id'],'stratum':c['stratum'],'side':side,**entry})
 for j,(af,rf) in enumerate(zip(ar['focus_flags'],rr['focus_flags'])):
  assert af['focus_index']==rf['focus_index']==j
  if (af['compound'],af['unassessable'])!=(rf['compound'],rf['unassessable']):disagreements.append({'case_id':c['case_id'],'focus_index':j,'author':af,'root':rf})
  focus=c['focuses'][j]
  for reviewer,ref in [('author',ar),('root',rr)]:
   expected=all(focus[s+'_indices'] and all(next(x['role'] for x in ref[s] if x['index']==i)=='NOUN' for i in focus[s+'_indices']) for s in ('source','target'));actual=all(focus[s+'_indices'] and all(models[key(c['pair'][s])]['tokens'][i][2]=='NOUN' for i in focus[s+'_indices']) for s in ('source','target'));m=focuscounts[(reviewer,c['stratum'])];m['focus_relations']+=1;m['reference_both_sides_all_noun']+=expected;m['model_both_sides_all_noun']+=actual;m['false_noun_only_rejection']+=expected and not actual;m['false_noun_only_acceptance']+=actual and not expected
 cases.append(out)
result={'inputs':{str(f):sha(f) for f in [W/'packet.json',W/'role-rubric.json',W/'author-review-r01.json',W/'root-review-r01.json',W/'outputs-r02/annotations.jsonl',W/'outputs-r02/receipt.json']},'cases':cases,'disagreements':disagreements,'model_errors_against_each_review':errors,'token_metrics':[{'reviewer':k[0],'stratum':k[1],'side':k[2],**v} for k,v in counts.items()],'hypothetical_noun_only_focus_metrics':[{'reviewer':k[0],'stratum':k[1],**v} for k,v in focuscounts.items()],'limits':'Reused diagnostic32pairs; no population accuracy, no gold/majority. All-token noun-only focus check is accounting, not a selector or eligibility change; broad alignments include function words. Compound/name evidence remains separate.'}
file=W/'joined-comparison.json'
with file.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
print('joined',sha(file),'disagreements',len(disagreements));print(json.dumps(result['token_metrics']));print(json.dumps(result['hypothetical_noun_only_focus_metrics']));print('errors',json.dumps([e for e in errors if e['reviewer']=='author'],ensure_ascii=False))
