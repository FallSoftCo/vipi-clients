#!/usr/bin/env python3
"""Exact correction delta; retain all changed full outputs and every method binding."""
import json,hashlib,sys,collections
from pathlib import Path
W=Path('/home/ai/Development/investigations/vipi-starter-content-expansion-20261109-r01')
def enc(x):return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):
 r=[json.loads(s) for s in p.read_text().splitlines() if s.strip()];d={(x['pair'],x['id'],x['state']):x for x in r};assert len(d)==len(r)==1386;return d
def main():
 files={'android':(W/'android-capture-r01/output.stdout',W/'android-capture-r02/output.stdout'),'apple':(W/'apple-run-r01/attachments/29E9F817-1BB6-42BD-A72B-76FD7DF13AF3',Path(sys.argv[1]))}
 groups=collections.defaultdict(dict);bindings=[];deltas=[];counts=collections.Counter();source={}
 for platform,(old,new) in files.items():
  a,b=rows(old),rows(new);assert a.keys()==b.keys()
  for key in a:
   x,y=a[key],b[key];assert all(x[k]==y[k] for k in ['source','known_ids','native_words','state','stratum']);source[key[:2]]=y
   xs={s['density_bits']:s for s in x['steps']};ys={s['density_bits']:s for s in y['steps']};assert xs.keys()==ys.keys()
   for bits in xs:
    for arm in ['current','candidate']:
     before=x['outputs'][xs[bits]['arms'][arm]['output']];after=y['outputs'][ys[bits]['arms'][arm]['output']]
     for kind in ['direct','route']:
      p={k:before[kind+'_'+k] for k in ['spans','mixed']};q={k:after[kind+'_'+k] for k in ['spans','mixed']};counts[platform+'/'+arm+'/'+kind+'/compared']+=1
      if p==q:continue
      counts[platform+'/'+arm+'/'+kind+'/changed']+=1
      assert arm=='candidate','Unexpected current-arm output change'
      bk=key[:2];link={'platform':platform,'pair':key[0],'id':key[1],'state':key[2],'density_bits':bits,'kind':kind,'arm':arm}
      for phase,value in [('original',p),('corrected',q)]:
       h=hashlib.sha256(enc(value)).hexdigest();groups[bk][h]=value;bindings.append({**link,'phase':phase,'option_hash':h})
      oldset={enc(s):s for s in p['spans']};newset={enc(s):s for s in q['spans']};deltas.append({**link,'source':y['source'],'before':p,'after':q,'added':[newset[k] for k in sorted(newset.keys()-oldset.keys())],'lost':[oldset[k] for k in sorted(oldset.keys()-newset.keys())]})
 out=W/'review-r02';assert not out.exists();out.mkdir();cases=[];labels={}
 for k,opts in sorted(groups.items()):
  order=sorted(opts,key=lambda h:hashlib.sha256(('content-correction-r02/'+str(k)+'/'+h).encode()).hexdigest());options=[]
  for i,h in enumerate(order):
   label=f'option-{i+1:02d}';labels[k+(h,)]=label;options.append({'label':label,**opts[h],'zero_immersion':not opts[h]['spans']})
  cases.append({'pair':k[0],'id':k[1],'source':source[k]['source'],'stratum':source[k]['stratum'],'options':options})
 for b in bindings:b['label']=labels[b['pair'],b['id'],b.pop('option_hash')]
 (out/'anonymous-packet.json').write_bytes(enc({'schema':1,'scope':'Every changed full output in the fixed corrected native comparison; all sources previously exposed. No fresh sample or population claim.','cases':cases}))
 (out/'method-key.json').write_bytes(enc(bindings));(out/'all-deltas.json').write_bytes(enc(deltas))
 receipt={'code_sha256':sha(Path(__file__)),'input_bindings':{p: {'original':sha(a),'corrected':sha(b)} for p,(a,b) in files.items()},'counts':dict(counts),'cases':len(cases),'options':sum(len(c['options']) for c in cases),'packet_sha256':sha(out/'anonymous-packet.json'),'key_sha256':sha(out/'method-key.json'),'delta_sha256':sha(out/'all-deltas.json'),'current_arm_all_outputs_identical':True,'activation':False};(out/'receipt.json').write_bytes(enc(receipt));print(enc(receipt).decode())
if __name__=='__main__':main()
