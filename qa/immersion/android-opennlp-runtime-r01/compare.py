from pathlib import Path
import json,hashlib,sys
p=Path('/home/ai/Development/investigations/vipi-android-opennlp-runtime-20261108-r01');variant=sys.argv[1];d=p/variant.lower()
read=lambda f:[json.loads(x) for x in Path(f).read_text().splitlines()]
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
assert sha('/home/ai/Development/investigations/vipi-android-source-annotations-20261108-r01/annotations.jsonl')=='5de5ba4efc6ba0696ca0999ccee86640d3949ac6e4629709fe4c8f3e34fa7910'
assert sha('/home/ai/Development/investigations/vipi-source-role-veto-20261108-r01/android/annotations.jsonl')=='d74ad01af3d62c969993a96f2c10d51ad6a25986af2e5b8cbf8e9711c61776fe'
inputs=p/'project/app/src/main/assets/inputs.json';freeze=json.loads((p/'resume-freeze-r02.json').read_text());assert sha(inputs)==freeze['id_text_only_input_sha256']
cases=json.loads(inputs.read_text())['cases'];expected_ids=[c['id'] for c in cases];assert len(cases)==148 and len(set(expected_ids))==148;source={c['id']:c['text'] for c in cases}
reference={x['id']:x for x in read('/home/ai/Development/investigations/vipi-android-source-annotations-20261108-r01/annotations.jsonl') if x['pass']==0}
broad={x['id']:x for x in read('/home/ai/Development/investigations/vipi-source-role-veto-20261108-r01/android/annotations.jsonl') if x['pass']==0}
rows=read(d/'annotations.jsonl');assert len(rows)==444
passes=[[{k:v for k,v in x.items() if k!='pass'} for x in rows if x['pass']==i] for i in range(3)];assert all([r['id'] for r in group]==expected_ids for group in passes)
for r in rows:
 original=source[r['id']].encode('utf-16-le')
 for sentence in r['sentences']:
  assert original[sentence['start']*2:sentence['end']*2].decode('utf-16-le')==sentence['text']
  for t in sentence['tokens']:assert 0<=t['start']<t['end']<=len(original)//2 and original[t['start']*2:t['end']*2].decode('utf-16-le')==t['text']
x={'variant':variant,'repeat_equal':passes[0]==passes[1]==passes[2],'cases':148,'failures':[],'max_POS_score_absolute_delta':0,'tokens':0,'exact_expected_ids_order_each_pass':True,'original_UTF16_substrings_independently_verified':True,'POS_score_tolerance':1e-12,'score_tolerance_is_numerical_parity_only_not_semantic_confidence':True}
for r in passes[0]:
 tokens=[t for s in r['sentences'] for t in s['tokens']];got=[(t['start'],t['end'],t['pos'],t['pos_score']) for t in tokens];rid=r['id']
 if rid in reference:
  old=reference[rid];want=[(t['start'],t['end'],t['pos'],t['pos_score']) for s in old['sentences'] for t in s['tokens']]
 else:want=[tuple(t) for t in broad[rid]['tokens']]
 if [a[:3] for a in got]!=[a[:3] for a in want]:x['failures'].append({'id':rid,'reason':'geometry/rawPOS mismatch'})
 else:
  delta=max([abs(a[3]-b[3]) for a,b in zip(got,want)]+[0]);x['max_POS_score_absolute_delta']=max(x['max_POS_score_absolute_delta'],delta)
  if delta>1e-12:x['failures'].append({'id':rid,'reason':'POSscore difference','absolute_delta':delta})
 x['tokens']+=len(tokens)
x['all_POS_scores_within_tolerance']=not any(r['reason']=='POSscore difference' for r in x['failures']);x['all_raw_POS_and_geometry_equal']=not any(r['reason']=='geometry/rawPOS mismatch' for r in x['failures']);x['native_receipt']=json.loads((d/'receipt.json').read_text());x['output_sha256']=hashlib.sha256((d/'annotations.jsonl').read_bytes()).hexdigest();x['wall_time_scope']='Native per-pass wall_ns is end-to-end probe wall time including JSON, local file writes, instrumentation sendStatus Binder/ADB transport; not isolated inference latency.';x['limits']='Runtime parity of reused source fixtures; no source-role accuracy, sense approval, API28, ARM64 or phone timing claim.'
(d/'comparison.json').write_text(json.dumps(x,indent=2)+'\n');print(json.dumps({k:v for k,v in x.items() if k!='native_receipt'},indent=2))
