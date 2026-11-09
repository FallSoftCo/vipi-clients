#!/usr/bin/env python3
import json,hashlib,collections
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-starter-packing-density-20261109-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
a=json.loads((W/'author-review-r01.json').read_text());r=json.loads((W/'root-review-r01.json').read_text())
assert sha(W/'author-review-r01.json')=='97dc08d3f9995b10c4ed71f40f130e512c602e905e286ae78c78785d91ae3e9a'
assert sha(W/'root-review-r01.json')=='698fb20f592e448c68d0b926bfa44643a89d423f600ab354f634b7d34c947878'
assert a['packet_sha256']==r['packet_sha256']
root={(g['pair'],g['id'],o['variant_id']):o for g in r['groups'] for o in g['options']};rows=[];counts={'author':collections.Counter(),'root':collections.Counter()};dis=[];novel={}
for g in a['cases']:
 for o in g['options']:
  key=(g['pair'],g['id'],o['variant_id']);other=root.pop(key);lab=other['judgment'];norm='minor_issue' if lab=='minor' else lab
  row={'pair':key[0],'id':key[1],'variant_id':key[2],'author':o,'root':other,'normalized_equal':o['label']==norm};rows.append(row)
  counts['author'][o['label']]+=1;counts['root'][norm]+=1
  if not row['normalized_equal']:dis.append(row)
  for u in o['units']:
   if u['novel']:novel[(key[:2],tuple(u['source_utf16']),u['target'],u['reading'])]=u['label']
assert not root and len(rows)==200 and len(novel)==83
out={'schema':1,'review_bindings':{'author':sha(W/'author-review-r01.json'),'root':sha(W/'root-review-r01.json'),'packet':a['packet_sha256']},'normalization':'minor -> minor_issue for comparison only; all original labels retained.','option_counts':counts,'author_novel_occurrence_counts':collections.Counter(novel.values()),'disagreements':dis,'rows':rows,'semantic_gold':False,'activated':False}
p=W/'joined-review-r01.json';assert not p.exists();p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'counts':counts,'disagreements':len(dis),'author_novel':out['author_novel_occurrence_counts'],'sha256':sha(p)}))
