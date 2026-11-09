#!/usr/bin/env python3
"""Join immutable agent judgments by exact source/output, retaining all differences."""
import json,hashlib,collections
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-starter-content-expansion-20261109-r01')
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(x):return {'minor':'minor_issue','material':'material_error','material_meaning_error':'material_error'}.get(x,x)
def main():
 reviews={};labels={};disagreements=[];inputs={}
 for rev,names in [('original',{'author':'author-review-r01.json','root':'root-review-r01.json'}),('delta',{'author':'author-delta-review-r02.json','root':'root-delta-review-r02.json'})]:
  packet=W/('review-r01' if rev=='original' else 'review-r02')/'anonymous-packet.json'; p=json.loads(packet.read_text());inputs[str(packet)] = sha(packet)
  for who,n in names.items():
   path=W/n;r=json.loads(path.read_text());assert r['packet_sha256']==sha(packet);reviews[rev+'/'+who]=r;inputs[str(path)]=sha(path)
   indexed={(c['pair'],c['id'],o['label']):o for c in r['cases'] for o in c['options']}
   for c in p['cases']:
    for o in c['options']:
     k=(who,c['pair'],c['id'],enc({x:o[x] for x in ['spans','mixed']}));judgment=norm(indexed[c['pair'],c['id'],o['label']]['judgment'])
     if k in labels:assert labels[k]==judgment,(k,labels[k],judgment)
     labels[k]=judgment
  if rev=='delta':
   for c in p['cases']:
    for o in c['options']:
     k=(c['pair'],c['id'],enc({x:o[x] for x in ['spans','mixed']}))
     if labels['author',*k]!=labels['root',*k]:disagreements.append({'pair':k[0],'id':k[1],'option':o,'author':labels['author',*k],'root':labels['root',*k]})
 stats=collections.defaultdict(collections.Counter);paired=collections.defaultdict(collections.Counter)
 raw={'android':W/'android-capture-r02/output.stdout','apple':W/'apple-run-r02/attachments/B83CD7EA-8E5F-4441-95C3-56B713B45EE7'}
 for platform,path in raw.items():
  inputs[str(path)]=sha(path)
  for line in path.open():
   if not line.strip():continue
   r=json.loads(line)
   for step in r['steps']:
    if step['density'] not in [.25,.75]:continue
    for kind in ['direct','route']:
     outputs={a:{x:r['outputs'][step['arms'][a]['output']][kind+'_'+x] for x in ['spans','mixed']} for a in ['current','candidate']}
     for who in ['author','root']:
      base=(who,platform,r['pair'],r['state'],str(step['density']),kind); judgments={a:labels[who,r['pair'],r['id'],enc(v)] for a,v in outputs.items()}
      for a,v in outputs.items():
       c=stats[base+(a,)];c['rows']+=1;c[judgments[a]]+=1;c['nonempty']+=bool(v['spans']);c['units']+=len(v['spans']);c['native_words']+=sum(sum(lo>=s['source_utf16'][0] and hi<=s['source_utf16'][1] for lo,hi in r['native_words']) for s in v['spans'])
      c=paired[base];c['rows']+=1
      for label,allowed in [('strict',{'correct'}),('minor_tolerant',{'correct','minor_issue'})]:
       c[label+'_gains']+=judgments['candidate'] in allowed and judgments['current'] not in allowed;c[label+'_losses']+=judgments['current'] in allowed and judgments['candidate'] not in allowed
      old={enc(x) for x in outputs['current']['spans']};new={enc(x) for x in outputs['candidate']['spans']};c['added_units']+=len(new-old);c['lost_units']+=len(old-new)
 out=W/'joined-r02';assert not out.exists();out.mkdir()
 result={'schema':1,'inputs':inputs,'code_sha256':sha(Path(__file__)),'reviews_unchanged':reviews,'delta_disagreements':disagreements,'stats':[{'key':list(k),**v} for k,v in sorted(stats.items())],'paired':[{'key':list(k),**v} for k,v in sorted(paired.items())],'limits':'Exact unchanged outputs inherit frozen original agent labels; changed full outputs use independent delta labels. Reused diagnostic sources, not population accuracy or gold. Original minor disagreements remain unchanged. Empty is zero usefulness; exclusion states are not familiarity.'}
 assert not any(s.get('material_error',0) for s in result['stats'] if s['key'][-1]=='candidate')
 (out/'joined.json').write_text(enc(result)+'\n');print(enc({'sha256':sha(out/'joined.json'),'delta_disagreements':len(disagreements),'candidate_material_reviewed_outputs':0}))
if __name__=='__main__':main()
