#!/usr/bin/env python3
"""Reviewed data-only correction; original candidates and judgments stay immutable."""
import json,hashlib
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-starter-content-expansion-20261109-r01')
def enc(x):return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 reviews={'author-review-r01.json':'00054d888a7f325f5cde372f32efe3c736757c96f9d58efacb159a74f3004309','root-review-r01.json':'eddbed2b81627a59d88302a4622fddb2ead3b5e158a274b4006d4ac7aab6f996'}
 for name,h in reviews.items():assert sha(W/name)==h
 out=W/'candidates-r02';assert not out.exists();out.mkdir();bindings={};removed={};summary={}
 for lang,old,new,count,pin in [('ja','003','004',190,'ba6f5a31f091f46a4ca0c9050404cb22d22e6579cc7f8a5094faa21da391a625'),('sw','002','003',214,'ffdb67bd1f413b458e0503e5ac865e7c9ef320f120ae1d644280f66d29dd8ccb')]:
  parent=W/'candidates-r01'/f'starter-en-{lang}-{old}.json';assert sha(parent)==pin;pack=json.loads(parent.read_text());before={e['id']:e for e in pack['entries']};ids={f'word-en-{lang}-{s}' for s in ['apple','jobs','school']};assert ids<=before.keys()
  active=json.loads((W/'native-inputs-r02'/f'current-{lang}.json').read_text());assert not ids & {e['id'] for e in active['entries']}
  removed[lang]=[e for e in pack['entries'] if e['id'] in ids];pack['entries']=[e for e in pack['entries'] if e['id'] not in ids];assert len(pack['entries'])==count
  after={e['id']:e for e in pack['entries']};assert all(after[e['id']]==e for e in active['entries']);assert after[f'word-en-{lang}-job']==before[f'word-en-{lang}-job'];assert all(before[k]==v for k,v in after.items())
  pack['version']=f'starter-en-{lang}-{new}';pack['qualification_status']='reviewed_data_correction_awaiting_combined_native_check';pack['withheld_original_entry_ids']=sorted(set(pack['withheld_original_entry_ids'])|ids);pack['correction_parent_sha256']=pin;pack['correction_review_sha256']=reviews;pack['activation']=False
  file=out/(pack['version']+'.json');file.write_bytes(enc(pack));manifest={'schema':'vipi-source-starter-manifest-1','version':pack['version'],'file':file.name,'sha256':sha(file),'bytes':file.stat().st_size,'entries':count};(out/f'starter-{lang}-candidate-manifest.json').write_bytes(enc(manifest))
  proofs=W/'candidates-r01'/f'proofs-{lang}.json';original=json.loads(proofs.read_text());kept=[p for p in original if p['entry_id'] not in ids];assert len(original)-len(kept)==3;assert all(p['record_sha256']==after[p['entry_id']]['record_sha256'] for p in kept);(out/f'proofs-{lang}.json').write_bytes(enc(kept))
  bindings[str(parent)]=pin;bindings[str(proofs)]=sha(proofs);summary[lang]={'entries':count,'retained_active_entries':len(active['entries']),'removed_entry_ids':sorted(ids),'singular_job_unchanged':True,'all_retained_entry_objects_unchanged':True}
 (out/'withheld-records.json').write_bytes(enc({'reviews':reviews,'records':removed,'reason':'Apple/Jobs name collisions and school fish-collective ambiguity. Data-only withholding authorized by root; no case runtime rule.'}))
 packet=json.loads((W/'review-r01/anonymous-packet.json').read_text());author=json.loads((W/'author-review-r01.json').read_text());au={(c['pair'],c['id']):c for c in author['cases']};lost=[]
 for c in packet['cases']:
  seen=set()
  for o in c['options']:
   for s in o['spans']:
    if s['source'].lower() not in ['apple','jobs','school']:continue
    sid=enc(s)
    if sid in seen:continue
    seen.add(sid);j=next(u for u in au[c['pair'],c['id']]['units'] if all(u[k]==s[k] for k in s));lost.append({'pair':c['pair'],'id':c['id'],'source':c['source'],'span':s,'author_label':j['label'],'reason':j['reason']})
 assert len(lost)==16 and sum(x['author_label']=='correct' for x in lost)==10 and sum(x['author_label']=='material_error' for x in lost)==6
 (out/'observed-withheld-occurrences.json').write_bytes(enc({'scope':'Union of frozen reviewed options, not rerun predictions; packing backfills unknown until native replay.','occurrences':lost}))
 receipt={'schema':1,'code_sha256':sha(Path(__file__)),'input_bindings':bindings,'review_bindings':reviews,'root_instruction':'Data-only withholding of apple/jobs/school in both pairs, preserving singular job and every other record; await root literal correction before combined native check.','summary':summary,'files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in out.iterdir()},'native_run':False,'activation':False};(out/'receipt.json').write_bytes(enc(receipt));print(json.dumps({'receipt_sha256':sha(out/'receipt.json'),'packs':summary}))
if __name__=='__main__':main()
