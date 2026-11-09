from pathlib import Path
import json,hashlib,collections
w=Path('/home/ai/Development/investigations/vipi-taskmaster-source-first-20261109-r01');load=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();a=load(w/'author-review-r01.json');r=load(w/'root-review-r01.json');key={(x['id'],x['label']):x['method'] for x in load(w/'packet/method-key.json')};am={(x['id'],x['option']):x for x in a['options']};rm={(x['id'],x['option']):x for x in r['rows']};norm={'minor':'minor_issue','material':'material_error','empty':'unavailable'};counts={};paired={};dis=[]
for reviewer,rows in [('author',am),('root',rm)]:
 stats=collections.defaultdict(collections.Counter);cases=collections.defaultdict(dict)
 for k,x in rows.items():
  label=x.get('label',x.get('judgment'));label=norm.get(label,label);m=key[k];stats[m][label]+=1;cases[k[0]][m]=label
 counts[reviewer]={m:dict(v) for m,v in stats.items()};pair=collections.Counter()
 for case,methods in cases.items():
  for n,allowed in [('strict',{'correct'}),('minor_tolerant',{'correct','minor_issue'})]:
   before=methods['target_informed'] in allowed;after=methods['source_first'] in allowed
   pair[n+'_gains']+=after and not before;pair[n+'_losses']+=before and not after
 paired[reviewer]=dict(pair)
for k,x in rm.items():
 y=am[k];j=norm.get(x['judgment'],x['judgment'])
 if j!=y['label']:dis.append({'id':k[0],'option':k[1],'method':key[k],'author':y,'root':x})
lookup={}
for k,x in am.items():
 for u in x['units']:lookup[k[0],key[k],json.dumps(u['span'],sort_keys=True)]=u
change=collections.defaultdict(collections.Counter);events=[]
for d in load(w/'packet/deltas.json'):
 for event,m,field in [('added','source_first','added_source_first'),('lost','target_informed','lost_source_first')]:
  for s in d[field]:
   u=lookup[d['id'],m,json.dumps(s,sort_keys=True)];change[event][u['label']]+=1;events.append({'id':d['id'],'event':event,'unit':u})
raw=load(w/'run-r01/output.json');byid={x['id']:x for x in raw['cases']};provenance=[]
for k,x in am.items():
 if key[k]!='source_first':continue
 for u in x['units']:
  if u['label']=='correct':continue
  row=byid[k[0]];cs=[row['candidates'][i] for i in row['selection']['selected_indices'] if row['candidates'][i]['focus_utf16']==u['span']['source_utf16'] and row['candidates'][i]['target']==u['span']['target']];assert len(cs)==1
  c=cs[0];provenance.append({'id':k[0],'unit':u,'candidate':c,'ordinary':row['candidates'].index(c)<row['ordinary_count'],'gates':row['gates'],'assessments':row['assessments'],'source_roles':row['roles'],'source_masks':row['source_masks']})
result={'review_hashes':{'author':sha(w/'author-review-r01.json'),'root':sha(w/'root-review-r01.json')},'counts':counts,'paired':paired,'disagreements':dis,'added_lost_frozen_author_labels':{k:dict(v) for k,v in change.items()},'emission_events':events,'source_first_noncorrect_candidate_provenance':provenance,'no_majority_gold':True};(w/'joined-review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['disagreements','emission_events','source_first_noncorrect_candidate_provenance']},indent=2));print('disagreements',[(x['id'],x['option'],x['author']['label'],x['root']['judgment']) for x in dis]);print('provenance',[(x['id'],x['unit']['span'],x['unit']['label'],x['ordinary'],x['candidate']['source_key']) for x in provenance])
