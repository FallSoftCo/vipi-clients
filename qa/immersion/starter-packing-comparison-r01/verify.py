#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,collections,time
Q=Path(__file__).resolve().parent;W=Path('/home/ai/Development/investigations/vipi-starter-packing-comparison-20261109-r01');R=Q.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 start=time.monotonic();raw=W/'android-capture-r01/output.stdout';d=json.loads(raw.read_text());spec=json.loads((W/'inputs/packing-input-manifest.json').read_text());packs={};old={};stats=collections.defaultdict(collections.Counter);unique=collections.defaultdict(set);heads=collections.defaultdict(collections.Counter)
 for lang in ('ja','sw'):
  inp=W/'inputs'/spec[lang]['file'];assert sha(inp)==spec[lang]['sha256'];a=json.loads(inp.read_text());old[lang]={(x['id'],x['known_state']):x for x in a['cases']};manifest=json.loads((R/'data/immersion'/('starter-catalog.json' if lang=='ja' else 'starter-sw-catalog.json')).read_text());p=R/'data/immersion'/manifest['file'];assert sha(p)==a['pack_sha256'];packs[lang]={e['id']:e for e in json.loads(p.read_text())['entries']}
 def sig(s):return (tuple(s['source_utf16']),s['source'],s['target'],s['reading'])
 for r in d['cases']:
  lang=r['pair'][3:];prev=old[lang][r['id'],r['known_state']];assert r['trace']==prev['trace'] and r['native_words']==prev['native_words'] and r['a_spans']==prev['spans'] and r['a_direct']==prev['starter_spans'] and r['a_mixed']==prev['mixed']
  entries=packs[lang];order=[(i,t) for i,t in enumerate(r['trace']) if t['reason'] is None];order.sort(key=lambda it:(entries[it[1]['entry_id']]['category']!='content',entries[it[1]['entry_id']]['train_rank'],-len(entries[it[1]['entry_id']]['source_tokens']),it[1]['source_utf16'][0]))
  chosen=[];used=0;audit=[]
  for ordinal,t in order:
   a,b=t['source_utf16'];e=entries[t['entry_id']];assert e['record_sha256']==t['record_sha256'] and e['target']==t['target'] and e['concept_id']==t['concept_id'];cost=sum(a<=x and y<=b for x,y in r['native_words']);assert cost>0
   reason='selected_overlap' if any(a<z['source_utf16'][1] and z['source_utf16'][0]<b for z in chosen) else 'remaining_native_budget' if used+cost>r['budget'] else None
   audit.append({'entry_id':t['entry_id'],'scope':[a,b],'cost':cost,'ordinal':ordinal,'reason':reason})
   if reason is None:chosen.append(t);used+=cost
  assert audit==r['admission'];assert used<=r['budget'];expected={sig(t) for t in chosen};assert expected=={sig(t) for t in r['b_direct']},r['id']
  assert r['b_direct']==r['b_spans'],'route differs from direct';baseline={sig(x) for x in r['a_spans']};after={sig(x) for x in r['b_spans']};assert baseline<=after
  for s in r['b_spans']:
   a,b=s['source_utf16'];t=next(t for t in chosen if sig(t)==sig(s));output=t['entry_id']+f'@{a}:{b}'
   for rec in r['recognitions']:
    mask=rec['mask']
    if mask and a<mask[1] and mask[0]<b:assert rec['mode']!='AMBIGUOUS' and {'id':output,'scope':[a,b]} in rec['approved']
   if sig(s) not in baseline:
    e=entries[t['entry_id']];k=r['pair'];stats[k][e['category']]+=1;heads[k][e['concept_id']]+=1;unique[k].add((r['id'],a,b,s['target']))
 out={'complete':True,'baseline_rows':768,'native_admission_orders':768,'mask_permissions_verified':True,'all_direct_to_route_equal':True,'all_original_spans_preserved':True,'added_categories':{k:dict(v) for k,v in stats.items()},'added_concepts':{k:dict(v) for k,v in heads.items()},'unique_added_source_occurrences_ignoring_exclusion_state':{k:len(v) for k,v in unique.items()},'raw_sha256':sha(raw),'verifier_sha256':sha(Path(__file__)),'seconds':time.monotonic()-start,'method':'Independent reconstruction from immutable actual native ranges/traces and exact published entry records; no tokenizer emulation or inference rerun.'}
 p=W/'mechanical-verification-r01.json';assert not p.exists();p.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
