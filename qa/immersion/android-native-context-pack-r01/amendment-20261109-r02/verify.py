#!/usr/bin/env python3
"""Offline result verification. Does not invoke Android, models or network."""
from pathlib import Path
import argparse,json,hashlib,collections
Q=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('stdout',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 assert not a.output.exists()
 freeze=json.loads((Q/'amendment-freeze.json').read_text())
 for name,h in freeze['source_hashes'].items():assert sha(Q/name)==h,name
 groups=collections.defaultdict(list)
 for line in a.stdout.read_text().splitlines():
  if 'CONTEXT_ROW:' in line:
   x=json.loads(line.split('CONTEXT_ROW:',1)[1]);groups[x['kind']].append(x['value'])
 assets=Q/'app/src/main/assets'
 fixtures=json.loads((assets/'rule-fixtures.json').read_text())['rows'];rules=groups['rule']
 assert [r['rule_id'] for r in rules]==[r['rule_id'] for r in fixtures]
 assert [r['index'] for r in rules]==list(range(1157))
 full=json.loads((assets/'full-sources.json').read_text())['cases'];observed=groups['full_source']
 assert [r['case_id'] for r in observed]==[r['case_id'] for r in full]
 assert [r['index'] for r in observed]==list(range(52))
 inputs=json.loads((assets/'role-inputs.json').read_text())['cases'];role=groups['role']
 assert [r['id'] for r in role]==[r['id'] for r in inputs]
 assert [r['index'] for r in role]==list(range(148))
 reference=Path('/home/ai/Development/investigations/vipi-android-opennlp-runtime-20261108-r01/release/annotations.jsonl')
 assert sha(reference)=='62132387b036d3b084f2789d38369dd029897b46383fe28acff8e0b182eca5ab'
 prior=[r for line in reference.read_text().splitlines() if (r:=json.loads(line))['pass']==0]
 assert [r['id'] for r in prior]==[r['id'] for r in inputs]
 maxdiff=0.0;failures=[]
 for c,r,old in zip(inputs,role,prior):
  assert r['source_sha256']==hashlib.sha256(c['text'].encode()).hexdigest()
  raw=c['text'].encode('utf-16-le');expected=[t for s in old['sentences'] for t in s['tokens']]
  assert len(expected)==len(r['tokens'])
  for t,want in zip(r['tokens'],expected):
   start,length=t['range'];end=start+length
   assert raw[start*2:end*2].decode('utf-16-le')==t['text']
   if (start,end,t['tag'],t['text'])!=(want['start'],want['end'],want['pos'],want['text']):failures.append({'id':c['id'],'reason':'raw_geometry_tag_text'})
   maxdiff=max(maxdiff,abs(t['score']-want['pos_score']))
 # Report actual recognition/guard observations against the same source-only
 # reference masks, but do not turn expected differences into silent approval.
 guard_differences=[]
 for c,r in zip(full,observed):
  assert r['snapshot']['original']==c['source']
  assert r['snapshot']['supplied']==[[x[0],x[1]-x[0]] for x in c['protected_ranges_utf16']]
  units=r['snapshot']['units']
  for mask in c.get('source_masks',[]):
   a0,b=mask['utf16'];matching=[u for u in units if u['range']==[a0,b-a0]]
   if not matching:guard_differences.append({'case_id':c['case_id'],'range':[a0,b-a0],'reason':'reference_unit_not_recognized'});continue
   guard=mask.get('guard') or {}
   for native,key in [('source_blocked','blocked'),('target_blocked','target_blocked'),('protects_inner','protect_inner')]:
    if key in guard and not any(u[native]==bool(guard[key]) for u in matching):guard_differences.append({'case_id':c['case_id'],'range':[a0,b-a0],'reason':'guard_flag_difference','flag':key})
 result={'status':'raw_runtime_verification_only','counts':{k:len(v) for k,v in groups.items()},'raw_tag_range_failures':failures,
         'score_max_abs_difference':maxdiff,'score_tolerance':1e-12,'score_pass':maxdiff<=1e-12,
         'rule_geometry_differences':[r['rule_id'] for r in rules if not r.get('whole_native_geometry_equal',False)],
         'rule_expected_differences':[r['rule_id'] for r in rules if not r.get('expected_equal',False)],
         'source_reference_guard_differences':guard_differences,'nil_focus_occurrences':sum(f['intrinsic'] is None for r in observed for u in r['snapshot']['units'] for f in u['forms']),
         'source_recognition_scope':'Compared emitted source-only reference units/flags; not a claim all Android/Apple loader internals are identical. Original masks remain distinct from new observation snapshots.',
         'semantic_approval':False,'named_protection':'unavailable','stdout_sha256':sha(a.stdout)}
 a.output.write_text(json.dumps(result,indent=2)+'\n')
 assert not failures and maxdiff<=1e-12
if __name__=='__main__':main()
