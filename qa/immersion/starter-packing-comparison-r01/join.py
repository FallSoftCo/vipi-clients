#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,collections
W=Path('/home/ai/Development/investigations/vipi-starter-packing-comparison-20261109-r01');Q=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 paths={k:W/v for k,v in {'author':'author-review-r01.json','root':'root-review-r01.json','packet':'comparison-r01/anonymous-packet.json','subset':'comparison-r01/root-anonymous-subset.json','key':'comparison-r01/method-key.json','raw':'android-capture-r01/output.stdout'}.items()};d={k:json.loads(p.read_text()) for k,p in paths.items()}
 assert d['author']['packet_sha256']==sha(paths['packet']) and d['root']['packet_sha256']==sha(paths['subset'])
 key={x['id']:x['methods'] for x in d['key']['cases']};packet={x['id']:x for x in d['packet']['cases']};reviews={who:{c['id']:{o['option']:o for o in c['options']} for c in d[who]['cases']} for who in ('author','root')};summary={};disagreements=[];raw_label_differences=[]
 norm=lambda label:'minor_issue' if label=='minor' else label
 for who,cases in reviews.items():
  counts=collections.defaultdict(collections.Counter);added=collections.defaultdict(collections.Counter)
  for cid,opts in cases.items():
   c=packet[cid];pair=c['pair'];ast=key[cid]['a'];bst=key[cid]['b']
   for arm,op in [('a',ast),('b',bst)]:counts[pair+'/'+arm][norm(opts[op]['label'])]+=1
   a=next(o for o in c['options'] if o['option']==ast);b=next(o for o in c['options'] if o['option']==bst);before={(tuple(s['source_utf16']),s['target']) for s in a['spans']}
   labels={(tuple(u.get('source_utf16',u.get('scope'))),u['target']):u for u in opts[bst]['units']}
   for s in b['spans']:
    k=(tuple(s['source_utf16']),s['target'])
    if k not in before:added[pair][norm(labels[k]['label'])]+=1
  summary[who]={'cases':len(cases),'whole_outputs_by_pair_arm':{k:dict(v) for k,v in counts.items()},'added_units_reviewed_by_pair':{k:dict(v) for k,v in added.items()}}
 for cid,opts in reviews['root'].items():
  for label,root in opts.items():
   author=reviews['author'][cid][label];au={(tuple(u['source_utf16']),u['target']):u for u in author['units']};ru={(tuple(u['scope']),u['target']):u for u in root['units']};assert au.keys()==ru.keys()
   units=[{'scope':k[0],'target':k[1],'author':au[k],'root':ru[k]} for k in au if norm(au[k]['label'])!=norm(ru[k]['label'])]
   if author['label']!=root['label']:raw_label_differences.append({'id':cid,'option':label,'author_label':author['label'],'root_label':root['label'],'normalized_equal':norm(author['label'])==norm(root['label'])})
   if norm(author['label'])!=norm(root['label']) or units:disagreements.append({'id':cid,'option':label,'methods':[m for m,x in key[cid].items() if x==label],'author':author,'root':root,'units':units})
 concepts=collections.defaultdict(lambda:collections.defaultdict(set));occurrences=collections.defaultdict(collections.Counter)
 for r in d['raw']['cases']:
  k=r['pair']+'/state-'+str(r['known_state']);tr={(tuple(t['source_utf16']),t['target']):t for t in r['trace']}
  for arm in ('a','b'):
   concepts[k][arm]
   for s in r[arm+'_spans']:
    t=tr[tuple(s['source_utf16']),s['target']];concepts[k][arm].add(t['concept_id']);occurrences[k+'/'+arm][t['concept_id']]+=1
 diversity={k:{'a_concepts':len(v['a']),'b_concepts':len(v['b']),'new_concept_ids':sorted(v['b']-v['a']),'a_ids':sorted(v['a']),'b_ids':sorted(v['b'])} for k,v in concepts.items()}
 out={'schema':1,'bindings':{k:{'path':str(p),'sha256':sha(p)} for k,p in paths.items()},'review_summary':summary,'disagreements':disagreements,'raw_label_differences':raw_label_differences,'label_normalization':{'minor':'minor_issue','original_review_files_unchanged':True},'prior_raw_label_join_sha256':sha(W/'joined-review-r01.json'),'diversity':diversity,'concept_occurrences':{k:dict(v) for k,v in occurrences.items()},'limits':'Independent agent judgments, no majority gold. Root predetermined subset only; author full packet. Prior sources/design exposed; visible unit count can reveal treatment. Empty means zero usefulness. All prior reviews immutable.','joiner_sha256':sha(Path(__file__))}
 p=W/'joined-review-r02.json';assert not p.exists();p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'summary':summary,'disagreements':len(disagreements),'diversity':{k:{x:y for x,y in v.items() if x not in ('a_ids','b_ids')} for k,v in diversity.items()}},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
