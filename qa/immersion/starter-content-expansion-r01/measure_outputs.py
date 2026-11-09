#!/usr/bin/env python3
"""Read-only native output accounting, with all changes retained."""
import json,hashlib,collections,statistics
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-starter-content-expansion-20261109-r01')
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 paths={'android':W/'android-capture-r01/output.stdout','apple':W/'apple-run-r01/attachments/29E9F817-1BB6-42BD-A72B-76FD7DF13AF3'}
 out=W/'mechanics-r01';assert not out.exists();out.mkdir()
 inputs=json.loads((W/'inputs-r02/comparison-inputs.json').read_text());source={(p,c['id']):c for p,cs in inputs['pairs'].items() for c in cs}
 stats=collections.defaultdict(collections.Counter);concepts=collections.defaultdict(set);timings=collections.defaultdict(list);changes=[];shared={};geometry=[];differences=[]
 for platform,path in paths.items():
  seen=set()
  for line in path.open():
   if not line.strip():continue
   r=json.loads(line);rk=(r['pair'],r['id'],r['state']);assert rk not in seen;seen.add(rk);assert source[rk[:2]]['source']==r['source']
   for step in r['steps']:
    assert step['budget']==max(1,int(len(r['native_words'])*step['density']))
    if step['density'] not in [.25,.75]:continue
    sk=rk+(step['density'],);observed={}
    for arm,b in step['arms'].items():
     assert b['translation_calls']==0;z=r['outputs'][b['output']];trace=r['evidence'][b['evidence']]['trace']
     for kind in ['direct','route']:
      spans=z[kind+'_spans'];cost=0
      for s in spans:
       a,end=s['source_utf16'];assert r['source'].encode('utf-16-le')[2*a:2*end].decode('utf-16-le')==s['source']
       covered=[x for x in r['native_words'] if x[0]>=a and x[1]<=end];cost+=len(covered)
      if kind=='direct':assert cost<=step['budget'] and len(spans)<=128
      key=(platform,r['pair'],r['state'],str(step['density']),kind,arm)
      stats[key].update(rows=1,nonempty=bool(spans),units=len(spans),native_words=cost,source_words=len(r['native_words']))
      stats[key]['origin:'+str(z['origin'])]+=1
      for s in spans:
       hits=[t for t in trace if t['source_utf16']==s['source_utf16'] and t['target']==s['target']]
       for h in hits:concepts[key].add(h['concept_id'])
      observed[kind,arm]={'spans':spans,'mixed':z[kind+'_mixed']}
     timings[platform,'direct'].append(b['direct_ms']);timings[platform,'route'].append(b['route_ms'])
    for kind in ['direct','route']:
     a=observed[kind,'current'];b=observed[kind,'candidate'];old={enc(s):s for s in a['spans']};new={enc(s):s for s in b['spans']}
     if a!=b:changes.append({'platform':platform,'pair':r['pair'],'id':r['id'],'state':r['state'],'density':step['density'],'kind':kind,'source':r['source'],'before':a,'after':b,'added':[new[x] for x in sorted(new.keys()-old.keys())],'lost':[old[x] for x in sorted(old.keys()-new.keys())]})
    if platform=='android':shared[sk]=(r['native_words'],step['budget'],observed)
    else:
     a=shared[sk]
     if a[:2]!=(r['native_words'],step['budget']):geometry.append({'pair':r['pair'],'id':r['id'],'state':r['state'],'density':step['density'],'android_words':a[0],'apple_words':r['native_words'],'android_budget':a[1],'apple_budget':step['budget']})
     if a[2]!=observed:differences.append({'key':sk,'android':{str(k):v for k,v in a[2].items()},'apple':{str(k):v for k,v in observed.items()}})
  assert len(seen)==1386
 result={'schema':1,'input_sha256':{k:sha(v) for k,v in paths.items()},'code_sha256':sha(Path(__file__)),'main_density_stats':[{'key':list(k),**dict(v),'distinct_traced_concepts':len(concepts[k])} for k,v in sorted(stats.items())],'timings_ms':{str(k):{'n':len(v),'median':statistics.median(v),'max':max(v),'sum':sum(v)} for k,v in timings.items()},'main_density_platform_output_differences':len(differences),'main_density_geometry_or_budget_differences':len(geometry),'changes':len(changes),'scope':'Reused diagnostic sources; native raw availability is not semantic acceptance or population coverage. Tail state is exclusion, not familiarity.'}
 for name,value in [('metrics.json',result),('changes.json',changes),('platform-differences.json',differences),('geometry-differences.json',geometry)]:
  (out/name).write_text(enc(value)+'\n')
 print(enc({'platform_output_differences':len(differences),'geometry_differences':len(geometry),'changes':len(changes)}))
if __name__=='__main__':main()
