#!/usr/bin/env python3
"""Read-only occurrence accounting; no semantic judgments or native replay."""
from pathlib import Path
import json,hashlib,collections
W=Path('/home/ai/Development/investigations/vipi-predicate-units-20261109-r01')
B=Path('/home/ai/Development/investigations/vipi-contextual-sense-hold-20261109-r01/android-capture-r01/output.stdout')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def key(r):return (r['id'],r['pair'],r['density'])
def sig(s):return json.dumps(s,sort_keys=True,ensure_ascii=False)
def main():
 p=W/'android-capture-r01/output.stdout';receipt=json.loads((p.parent/'receipt.json').read_text());assert receipt['success']
 old={key(r):r for r in map(json.loads,B.open()) if r['pair']=='en-sw'}
 new={key(r):r for r in map(json.loads,p.open())};assert len(new)==160 and new.keys()==old.keys()
 changed=[];metrics={}
 for d in [.25,.75]:
  a=[old[k] for k in new if k[2]==d];b=[new[k] for k in new if k[2]==d]
  metrics[str(d)]={'rows':len(a),'baseline_nonempty':sum(bool(r['spans']) for r in a),'candidate_nonempty':sum(bool(r['spans']) for r in b),'baseline_spans':sum(len(r['spans']) for r in a),'candidate_spans':sum(len(r['spans']) for r in b)}
 for k,b in new.items():
  a=old[k]
  for f in ['source','native_words','known_ids','reference_hit']:assert a[f]==b[f],(k,f)
  assert b['translation_calls']==0 and b['error_class'] is None
  aa={sig(x):x for x in a['spans']};bb={sig(x):x for x in b['spans']}
  if a['spans']!=b['spans']:
   changed.append({'id':k[0],'pair':k[1],'density':k[2],'source':b['source'],'before':a['mixed_script'],'after':b['mixed_script'],'added':[bb[x] for x in bb.keys()-aa.keys()],'lost':[aa[x] for x in aa.keys()-bb.keys()],'baseline_spans':a['spans'],'candidate_spans':b['spans']})
 out={'schema':'vipi-positive-predicate-comparison-1','baseline_sha256':sha(B),'candidate_sha256':sha(p),'code_sha256':sha(Path(__file__)),'metrics':metrics,'changed_rows':len(changed),'unchanged_rows':160-len(changed),'deltas':changed,'semantic_acceptance':False}
 dest=W/'android-comparison-r01.json';assert not dest.exists();dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'metrics':metrics,'changed_rows':len(changed),'sha256':sha(dest)}))
if __name__=='__main__':main()
