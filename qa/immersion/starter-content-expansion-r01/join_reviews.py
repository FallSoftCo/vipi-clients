#!/usr/bin/env python3
"""Preserve both independent judgments; no majority approval."""
import json,hashlib,collections
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-starter-content-expansion-20261109-r01')
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(s):return {'minor':'minor_issue','material':'material_error'}.get(s,s)
def main():
 paths={'author':W/'author-review-r01.json','root':W/'root-review-r01.json'}
 expected={'author':'00054d888a7f325f5cde372f32efe3c736757c96f9d58efacb159a74f3004309','root':'eddbed2b81627a59d88302a4622fddb2ead3b5e158a274b4006d4ac7aab6f996'}
 for k,p in paths.items():assert sha(p)==expected[k]
 reviews={k:json.loads(p.read_text()) for k,p in paths.items()};packet=json.loads((W/'review-r01/anonymous-packet.json').read_text());key=json.loads((W/'review-r01/method-key.json').read_text())
 for r in reviews.values():assert r['packet_sha256']==sha(W/'review-r01/anonymous-packet.json')
 option={};units={};cases={};disagreements=[];unit_disagreements=[]
 for reviewer,review in reviews.items():
  cases[reviewer]={(c['pair'],c['id']):c for c in review['cases']}
  for c in review['cases']:
   for o in c['options']:option[reviewer,c['pair'],c['id'],o['label']]=norm(o['judgment'])
   for u in c.get('units',c.get('span_judgments',[])):
    s=u if reviewer=='author' else u['span'];sid=enc({k:s[k] for k in ['source','target','reading','source_utf16']});units[reviewer,c['pair'],c['id'],sid]=norm(u['label'] if reviewer=='author' else u['judgment'])
 for c in packet['cases']:
  pair,id=c['pair'],c['id'];ac=cases['author'][pair,id];rc=cases['root'][pair,id]
  for o in c['options']:
   if option['author',pair,id,o['label']]!=option['root',pair,id,o['label']]:disagreements.append({'pair':pair,'id':id,'source':c['source'],'option':o,'author':next(x for x in ac['options'] if x['label']==o['label']),'root':next(x for x in rc['options'] if x['label']==o['label'])})
  seen=set()
  for o in c['options']:
   for s in o['spans']:
    sid=enc(s)
    if sid in seen:continue
    seen.add(sid)
    if units['author',pair,id,sid]!=units['root',pair,id,sid]:unit_disagreements.append({'pair':pair,'id':id,'source':c['source'],'span':s,'author':units['author',pair,id,sid],'root':units['root',pair,id,sid]})
 mapping={(x['platform'],x['pair'],x['id'],x['state'],x['density_bits'],x['arm'],x['route']):x['label'] for x in key}
 stats=collections.defaultdict(collections.Counter);paired=collections.defaultdict(collections.Counter)
 raw={'android':W/'android-capture-r01/output.stdout','apple':W/'apple-run-r01/attachments/29E9F817-1BB6-42BD-A72B-76FD7DF13AF3'}
 for platform,path in raw.items():
  for line in path.open():
   if not line.strip():continue
   r=json.loads(line);pair,id,state=r['pair'],r['id'],r['state']
   for step in r['steps']:
    if step['density'] not in [.25,.75]:continue
    for route in ['direct','route']:
     outputs={arm:r['outputs'][step['arms'][arm]['output']][route+'_spans'] for arm in ['current','candidate']}
     sets={a:{enc(s):s for s in v} for a,v in outputs.items()}
     for reviewer in reviews:
      judgments={a:option[reviewer,pair,id,mapping[platform,pair,id,state,step['density_bits'],a,route]] for a in outputs}
      base=(reviewer,platform,pair,state,str(step['density']),route)
      for arm,spans in outputs.items():
       counter=stats[base+(arm,)];counter['rows']+=1;counter[judgments[arm]]+=1
       for s in spans:
        label=units[reviewer,pair,id,enc(s)];counter['emitted_units_'+label]+=1;counter['emitted_native_words_'+label]+=sum(a>=s['source_utf16'][0] and b<=s['source_utf16'][1] for a,b in r['native_words'])
      pc=paired[base];pc['rows']+=1
      for title,admitted in [('strict',{'correct'}),('minor_tolerant',{'correct','minor_issue'})]:
       a=judgments['current'] in admitted;b=judgments['candidate'] in admitted;pc[title+'_gains']+=b and not a;pc[title+'_losses']+=a and not b
      for kind,identities in [('added',sets['candidate'].keys()-sets['current'].keys()),('lost',sets['current'].keys()-sets['candidate'].keys())]:
       for sid in identities:pc[kind+'_'+units[reviewer,pair,id,sid]]+=1
 out=W/'joined-r01';assert not out.exists();out.mkdir()
 report={'schema':1,'inputs':{k:{'path':str(p),'sha256':sha(p)} for k,p in paths.items()},'packet_sha256':sha(W/'review-r01/anonymous-packet.json'),'key_sha256':sha(W/'review-r01/method-key.json'),'code_sha256':sha(Path(__file__)),'original_reviews':reviews,'option_disagreements':disagreements,'unit_disagreements':unit_disagreements,'stats':[{'key':list(k),**v} for k,v in sorted(stats.items())],'paired':[{'key':list(k),**v} for k,v in sorted(paired.items())],'interpretation':'Independent agents; all raw labels and disagreements retained. Reused/diagnostic inputs, no population accuracy, no majority gold. Empty zero usefulness; exclusions not familiarity. All raw outputs retained.'}
 (out/'joined.json').write_text(enc(report)+'\n');print(enc({'option_disagreements':len(disagreements),'unit_disagreements':len(unit_disagreements),'sha256':sha(out/'joined.json')}))
if __name__=='__main__':main()
