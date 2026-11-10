from pathlib import Path
import hashlib,json,statistics,collections
R=Path(__file__).resolve().parents[3];W=R.parent/'investigations/vipi-predicate-units-20261109-r01';C=W.parent/'vipi-conversation-depth-20261109-r01';H=W.parent/'vipi-contextual-sense-hold-20261109-r01'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:[json.loads(x) for x in p.read_text().splitlines() if x.strip()]
key=lambda r:f"{r['id']}:{r['pair']}:{r['density']}"
before={key(r):r for r in read(H/'apple-capture-r01/inputs-r01/apple-output.jsonl') if r['pair']=='en-sw'}
after={key(r):r for r in read(W/'apple-capture-r01/inputs-r01/apple-output.jsonl')}
assert len(before)==len(after)==160 and before.keys()==after.keys()
old={key(r):r for r in read(C/'apple-capture-r01/inputs-r01/apple-output.jsonl')}
bindings=json.loads((C/'review-r01/bindings.json').read_text());packet=json.loads((W/'review-packet-r01.json').read_text())
changed={f"{r['source_id']}:en-sw:{r['density']}":r for r in packet['cases'] if r['kind']=='conversation_change'}
unchanged=0
for k,r in after.items():
 assert r['source']==before[k]['source'] and r['native_words']==before[k]['native_words']
 if k not in changed:
  assert all(r[f]==before[k][f] for f in ['spans','mixed_script','mixed_reading']);unchanged+=1
assert unchanged==141

def counts(rows,labels):
 rows=list(rows);strict_messages=minor_messages=words=0;raw=[];correct=[];useful=[]
 for r in rows:
  label=labels[key(r)];n=len(r['native_words']);total=set();good=set()
  for index,s in enumerate(r['spans']):
   covered={i for i,(a,b) in enumerate(r['native_words']) if s['source_utf16'][0]<=a and b<=s['source_utf16'][1]};total|=covered
   if index in label['useful_span_indices']:good|=covered
  assert n>0;words+=len(total);raw.append(len(total)/n)
  strict=label['label']=='compatible';tolerant=label['label'] in ('compatible','minor')
  strict_messages+=int(strict and bool(good));minor_messages+=int(tolerant and bool(good))
  correct.append(len(total)/n if strict else 0);useful.append(len(good)/n if strict else 0)
 return {'messages':len(rows),'nonempty':sum(bool(r['spans']) for r in rows),'emitted_native_words':words,'native_words_total':sum(len(r['native_words']) for r in rows),'strict_useful_messages':strict_messages,'minor_inclusive_useful_messages':minor_messages,'macro_raw_depth':statistics.mean(raw),'macro_strict_correct_depth':statistics.mean(correct),'macro_strict_useful_depth':statistics.mean(useful)}
result={}
for reviewer in ['root','author']:
 prior=json.loads((C/f'{reviewer}-review-r01.json').read_text());new=json.loads((W/f'{reviewer}-review-r01.json').read_text());assert new['packet_sha256']==sha(W/'review-packet-r01.json')
 p={(r['case'],r['option']):r for r in prior['rows']};nr={r['id']:r for r in new['rows']};assert len(nr)==56
 base={}
 for k,r in before.items():
  b=bindings[k]
  if all(r[f]==old[k][f] for f in ['spans','mixed_script','mixed_reading']):base[k]=p[b['case'],b['option']]
  else:
   assert r['id']=='bst-valid-depth-r01-0878-10' and not r['spans'];base[k]={'label':'empty','useful_span_indices':[]}
 current={k:nr[changed[k]['id']] if k in changed else base[k] for k in after}
 result[reviewer]={str(d):{'before':counts([r for r in before.values() if r['density']==d],base),'after':counts([r for r in after.values() if r['density']==d],current)} for d in [.25,.75]}
root={r['id']:r for r in json.loads((W/'root-review-r01.json').read_text())['rows']};author={r['id']:r for r in json.loads((W/'author-review-r01.json').read_text())['rows']}
diff=[{'id':k,'root':root[k],'author':author[k]} for k in root if any(root[k][f]!=author[k][f] for f in ['label','useful_span_indices'])]
bound=[W/'review-packet-r01.json',W/'root-review-r01.json',W/'author-review-r01.json',C/'root-review-r01.json',C/'author-review-r01.json',C/'review-r01/bindings.json',H/'apple-capture-r01/inputs-r01/apple-output.jsonl',W/'apple-capture-r01/inputs-r01/apple-output.jsonl']
out={'schema':'vipi-predicate-reviewed-delta-1','all80_sources_per_density':True,'unchanged141_labels_transferred_only_after_exact_output_comparison':True,'hair_hold_baseline_empty_rows':2,'new_reviews':56,'exposed_development_sample_not_acceptance_population':True,'model_availability_forced_unavailable':True,'native_human_gold':False,'reviewers_retained_separately':True,'scores':result,'new_review_disagreements':diff,'bindings':{str(p):sha(p) for p in bound}}
p=W/'reviewed-scorecard-r01.json';assert not p.exists();p.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(result,indent=2));print('new_review_disagreements',len(diff))
