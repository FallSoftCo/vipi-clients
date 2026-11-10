#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,collections
W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def sk(s):return tuple(s['source_utf16'])+(s['source'],s['target'],s.get('reading'))
def main():
 out=W/'mechanics-r02';assert not out.exists();out.mkdir();allrows={};metrics={};deltas=[]
 for platform,path in [('android',W/'android-capture-r01/output.stdout'),('apple',W/'apple-run-r01/inputs-r02/frame-output.jsonl')]:
  rows=[json.loads(x) for x in path.read_text().splitlines()];assert len(rows)==656;allrows[platform]={(r['pair'],r['id'],r['state'],r['density']):r for r in rows};assert len(allrows[platform])==656
  for r in rows:
   words=r['native_words'];budget=max(1,int(len(words)*r['density'])) if r['density']>0 else 0
   for layer in ['direct','route']:
    m=metrics.setdefault((platform,r['pair'],r['state'],r['density'],layer),collections.Counter());m['rows']+=1;sets={}
    for arm in ['baseline','candidate']:
     spans=r[arm]['spans'] if layer=='direct' else r['route'][arm]['spans'];sets[arm]={sk(s) for s in spans};assert len(sets[arm])==len(spans);m[arm+'_nonempty']+=bool(spans);m[arm+'_units']+=len(spans)
     depth=0;last=-1
     for s in spans:
      a,b=s['source_utf16'];assert a>=last;last=b;assert r['source'].encode('utf-16-le')[2*a:2*b].decode('utf-16-le')==s['source'];inside=[w for w in words if a<=w[0] and w[1]<=b];assert inside and inside[0][0]==a and inside[-1][1]==b;depth+=len(inside)
     assert len(spans)<=128
     if layer=='direct':assert depth<=budget
     m[arm+'_over_adapter_floor_budget']+=depth>budget;m[arm+'_native_words']+=depth
    added=sets['candidate']-sets['baseline'];lost=sets['baseline']-sets['candidate'];m['changed_rows']+=bool(added or lost);m['added_units']+=len(added);m['lost_units']+=len(lost);m['empty_to_nonempty']+=not sets['baseline'] and bool(sets['candidate']);m['nonempty_to_empty']+=bool(sets['baseline']) and not sets['candidate']
    if added or lost:deltas.append({'platform':platform,'pair':r['pair'],'id':r['id'],'source':r['source'],'state':r['state'],'density':r['density'],'layer':layer,'added':sorted(added,key=str),'lost':sorted(lost,key=str)})
 differences=[]
 for k,a in allrows['android'].items():
  b=allrows['apple'][k]
  for layer in ['direct','route']:
   for arm in ['baseline','candidate']:
    x=a[arm]['spans'] if layer=='direct' else a['route'][arm]['spans'];y=b[arm]['spans'] if layer=='direct' else b['route'][arm]['spans']
    if [sk(s) for s in x]!=[sk(s) for s in y]:differences.append({'key':k,'layer':layer,'arm':arm,'android':x,'apple':y})
 result={'input_sha256':{p:sha(W/n) for p,n in [('android','android-capture-r01/output.stdout'),('apple','apple-run-r01/inputs-r02/frame-output.jsonl')]},'metrics':[dict(zip(['platform','pair','state','density','layer'],k),**v) for k,v in sorted(metrics.items())],'platform_selection_differences':differences,'native_geometry_different_rows':sum(a['native_words']!=allrows['apple'][k]['native_words'] for k,a in allrows['android'].items()),'interpretation':'Finite exposed diagnostic cases; raw availability/depth only, not semantic acceptance or population coverage.'}
 for n,x in [('summary.json',result),('all-deltas.json',deltas)]: (out/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
 (out/'receipt.json').write_text(json.dumps({'script_sha256':sha(Path(__file__)),'files':{n:sha(out/n) for n in ['summary.json','all-deltas.json']},'native_geometry_budget_nonoverlap_checked':True},indent=2)+'\n')
 print(json.dumps({'platform_selection_differences':len(differences),'native_geometry_different_rows':result['native_geometry_different_rows'],'delta_rows':len(deltas)}))
if __name__=='__main__':main()
