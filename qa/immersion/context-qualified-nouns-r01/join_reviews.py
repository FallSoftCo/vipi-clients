"""Join immutable agent labels without reconciling disagreements or producing gold."""
import json,pathlib,hashlib,collections
W=pathlib.Path('/home/ai/Development/investigations/vipi-context-qualified-nouns-20261109-r01')
def read(p):return json.loads((W/p).read_text())
def sig(u):return json.dumps([u['focus_utf16'],u['source'],u['target'],u['reading']],ensure_ascii=False,sort_keys=True)
def norm(label):return 'zero_immersion' if label=='unavailable_no_immersion' else 'minor_issue' if label=='minor_form' else label
p=read('packet/anonymous-packet.json');key={x['case_id']:x for x in read('packet/method-key.json')};reviews={n:read(n+'-review-r01.json') for n in ['author','root']};ridx={n:{c['case_id']:c for c in r['cases']} for n,r in reviews.items()};counts=collections.defaultdict(collections.Counter);changes=collections.defaultdict(collections.Counter);disagreements=[];joined=[]
for c in p['cases']:
 cid=c['case_id'];k=key[cid];group='development' if c['development_control'] else 'sampled';arms=k['methods'];entry={'case_id':cid,'group':group,'known':k['known'],'methods':arms,'reviews':{n:ridx[n][cid] for n in reviews}}
 for axis,idkey in [('options','option_id'),('emissions',None)]:
  aa={x[idkey] if idkey else sig(x):x for x in ridx['author'][cid][axis]};bb={x[idkey] if idkey else sig(x):x for x in ridx['root'][cid][axis]};assert aa.keys()==bb.keys()
  for ident in aa:
   if norm(aa[ident]['label'])!=norm(bb[ident]['label']):disagreements.append({'case_id':cid,'group':group,'axis':axis,'identity':ident,'author':aa[ident],'root':bb[ident]})
 for reviewer in reviews:
  rc=ridx[reviewer][cid];opts={x['option_id']:x for x in rc['options']};units={sig(x):x for x in rc['emissions']}
  sets={arm:{sig(u) for u in c['union_emissions'] if oid in u['option_ids']} for arm,oid in arms.items()}
  for arm,oid in arms.items():
   label=norm(opts[oid]['label']);co=counts['|'.join([group,reviewer,arm])];co['cases']+=1;co[label]+=1;co['nonempty']+=label!='zero_immersion';co['strict_nonempty']+=label=='correct';co['minor_tolerant_nonempty']+=label in ['correct','minor_issue']
  for other in ['baseline','unrestricted']:
   co=changes['|'.join([group,reviewer,'qualified_vs_'+other])];ql=norm(opts[arms['qualified']]['label']);ol=norm(opts[arms[other]]['label']);co['strict_gains']+=(ql=='correct' and ol!='correct');co['strict_losses']+=(ol=='correct' and ql!='correct')
   for direction,ids in [('added',sets['qualified']-sets[other]),('lost',sets[other]-sets['qualified'])]:
    for ident in ids:co[direction+'_'+norm(units[ident]['label'])]+=1
 joined.append(entry)
out={'input_hashes':{n:hashlib.sha256((W/n).read_bytes()).hexdigest() for n in ['packet/anonymous-packet.json','packet/method-key.json','author-review-r01.json','root-review-r01.json']},'no_majority_gold':True,'counts':{k:dict(v) for k,v in counts.items()},'paired_review_changes':{k:dict(v) for k,v in changes.items()},'disagreements':disagreements,'cases':joined}
pout=W/'joined-review-r01.json';assert not pout.exists();pout.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ['cases','disagreements']},indent=2));print('disagreements',len(disagreements))
