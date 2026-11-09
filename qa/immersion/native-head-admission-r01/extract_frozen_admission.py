#!/usr/bin/env python3
"""Prepared read-only extraction of already computed evidence; no selector/model call.
Run only under approved data-preparation plan. Never modifies original files.
"""
import json,gzip,pathlib,hashlib,argparse,time
p=argparse.ArgumentParser();p.add_argument('selection',type=pathlib.Path);p.add_argument('output',type=pathlib.Path);a=p.parse_args();start=time.monotonic()
inputs={'trace':('/srv/fallsoft/staging/vipi-source-name-scope-20261109-r01/outputs/project-r02/decisions.jsonl.gz','02a8fca6cb30a0a9912658ee17d92ae2eed50d5858ce5bc7b10376d90efe9e3b'),'lookup':('/srv/fallsoft/staging/vipi-context-qualified-nouns-20261109-r01/prepare/lookup.json','58880fd80deecb136e5bac8486ae8e454942ece39a0811ebce009182da764aa3'),'qualified':('/srv/fallsoft/staging/vipi-context-qualified-nouns-20261109-r01/project/decisions.jsonl.gz','e30cd4a919fab5a97286cb384bf10c1845cc9d519bdeba1bbda908488c18a1db')}
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  while b:=f.read(1048576):h.update(b)
 return h.hexdigest()
for path,h in inputs.values():assert sha(path)==h,path
selected=json.loads(a.selection.read_text());wanted={x['source_id'] for x in selected['cases']};lookup=json.loads(pathlib.Path(inputs['lookup'][0]).read_text());found={}
for name in ['trace','qualified']:
 rows={}
 with gzip.open(inputs[name][0],'rt') as f:
  for line in f:
   if time.monotonic()-start>60:raise TimeoutError('extraction deadline')
   r=json.loads(line)
   if r['id'] in wanted:rows[r['id']]=r
 assert set(rows)==wanted;found[name]=rows
out=[]
for item in selected['cases']:
 t=found['trace'][item['source_id']];q=found['qualified'][item['source_id']];assert t['text']==item['source'];assert t['native_words_utf16']==item['native_words_utf16'];assert t['source_masks']==item['source_masks'];assert t['protected_ranges_utf16']==item['protected_ranges_utf16'];scopes=[]
 for key,g in sorted(q['gates'].items()):
  cs=[t['candidates'][i] for i in g['candidate_indices']];keys=sorted({v for c in cs for v in lookup['head_keys'].get(c['head_id'],[])})
  scopes.append({'focus_utf16':json.loads(key),'source_keys':keys,'key_scope_identity':hashlib.sha256(json.dumps([item['source_id'],key,keys],sort_keys=True,separators=(',',':')).encode()).hexdigest(),'basis':'Frozen original gate candidate_indices -> original lookup.head_keys; not all-spelling key enumeration','original_gate':g,'original_candidates':cs,'original_admitted_head_ids':sorted({t['candidates'][i]['head_id'] for i in g['admitted_indices']})})
 assert len(scopes)<=16
 out.append({**item,'scopes':scopes,'original_qualified_selection':q['qualified']})
result={'schema':'vipi.native-head-admission.frozen-comparison.r01','inputs':inputs,'selection_sha256':sha(a.selection),'known_family_inputs':[],'no_new_inference_or_selection':True,'limits':'Original gates use frozen OpenNLP roles. Current Apple roles/native mask/window rules may differ; comparisons diagnose, never relabel. Original qualified_selection is post-known/budget; adapter is prebudget conditional evidence.','cases':out}
raw=(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n').encode();assert len(raw)<=4*1024*1024
with a.output.open('xb') as f:f.write(raw)
print(json.dumps({'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'cases':len(out),'scopes':sum(len(x['scopes']) for x in out),'seconds':time.monotonic()-start}))
