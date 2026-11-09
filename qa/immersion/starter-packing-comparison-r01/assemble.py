#!/usr/bin/env python3
"""Read-only mechanical comparison and physically separate method-blind packets."""
from pathlib import Path
import json,hashlib,collections
W=Path('/home/ai/Development/investigations/vipi-starter-packing-comparison-20261109-r01');Q=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):
 assert not p.exists(),p
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sk(s):return (tuple(s['source_utf16']),s['source'],s['target'],s.get('reading'))
def cost(row,spans):
 selected=set()
 for s in spans:
  a,b=s['source_utf16'];covered={i for i,(x,y) in enumerate(row['native_words']) if a<=x and y<=b};touched={i for i,(x,y) in enumerate(row['native_words']) if x<b and a<y}
  assert covered==touched and covered,(row['id'],s)
  selected|=covered
 return len(selected)
def main():
 raw=W/'android-capture-r01/output.stdout';d=json.loads(raw.read_text());assert d['complete'] and d['baseline_parity_rows']==768 and len(d['cases'])==768
 receipt=json.loads((W/'android-capture-r01/receipt.json').read_text());assert receipt['success'] and receipt['output_sha256']==sha(raw)
 protocol=sha(Q/'protocol.json');out=W/'comparison-r01';assert not out.exists();out.mkdir()
 metrics=collections.defaultdict(collections.Counter);packet=[];keys=[];deltas=[];group=collections.defaultdict(list)
 for index,r in enumerate(d['cases']):
  pair=r['pair'];state=r['known_state'];a=r['a_spans'];b=r['b_spans'];ak={sk(s) for s in a};bk={sk(s) for s in b}
  added=[s for s in b if sk(s) not in ak];lost=[s for s in a if sk(s) not in bk];changed=ak!=bk
  m=metrics[f'{pair}/state-{state}'];m.update(messages=1,native_source_words=len(r['native_words']),a_nonempty=bool(a),b_nonempty=bool(b),a_units=len(a),b_units=len(b),a_words=cost(r,a),b_words=cost(r,b),changed_messages=changed,empty_gains=not a and bool(b),empty_losses=bool(a) and not b,added_units=len(added),lost_units=len(lost),a_direct_units=len(r['a_direct']),b_direct_units=len(r['b_direct']))
  assert cost(r,r['b_direct'])<=r['budget']
  caseid=f'{pair}/{r["id"]}/state-{state}';group[(pair,r['id'])].append((caseid,changed))
  order=['a','b'] if int(hashlib.sha256((protocol+'\0'+caseid).encode()).hexdigest(),16)%2==0 else ['b','a'];opts=[];binding={}
  for arm in order:
   existing=next((o for o in opts if o['mixed']==r[arm+'_mixed'] and o['spans']==r[arm+'_spans']),None)
   if existing:binding[arm]=existing['option'];continue
   label=f'option-{len(opts)+1}';opts.append({'option':label,'mixed':r[arm+'_mixed'],'spans':r[arm+'_spans'],'zero_immersion':not r[arm+'_spans']});binding[arm]=label
  packet.append({'id':caseid,'source_id':r['id'],'pair':pair,'known_state':state,'excluded_concept_ids':r['known_ids'],'source':r['original'],'options':opts})
  keys.append({'id':caseid,'methods':binding,'origins':{x:r[x+'_origin'] for x in ['a','b']}})
  deltas.append({'id':caseid,'added':added,'lost':lost,'changed':changed,'native_budget':r['budget']})
 chosen=[];selection={}
 for pair in ['en-ja','en-sw']:
  rank=lambda k:hashlib.sha256((k[0]+'\0'+k[1]).encode()).hexdigest()
  groups=[k for k in group if k[0]==pair];changed=sorted([k for k in groups if any(v for _,v in group[k])],key=rank);same=sorted([k for k in groups if not any(v for _,v in group[k])],key=rank)
  select=changed[:20]+same[:4];chosen += [cid for k in select for cid,_ in group[k]]
  selection[pair]={'changed_source_ids_available':len(changed),'changed_source_ids_selected':[k[1] for k in changed[:20]],'control_source_ids_selected':[k[1] for k in same[:4]],'ranking':'SHA256(pair+NUL+source ID); no label/outcome-based backfill'}
 put(out/'anonymous-packet.json',{'schema':1,'historical_diagnostic':True,'cases':packet})
 put(out/'root-anonymous-subset.json',{'schema':1,'historical_diagnostic':True,'cases':[p for p in packet if p['id'] in chosen]})
 put(out/'method-key.json',{'methods':{'a':'unchanged one-unit normal route','b':'same-budget greedy packing normal route'},'cases':keys})
 put(out/'deltas.json',deltas);put(out/'metrics.json',{k:dict(v) for k,v in sorted(metrics.items())});put(out/'selection.json',selection)
 times={arm:{'sum_ms':sum(r[arm+'_ms'] for r in d['cases']),'max_ms':max(r[arm+'_ms'] for r in d['cases'])} for arm in ['a','b']};put(out/'timing.json',times)
 put(out/'receipt.json',{'raw_sha256':sha(raw),'protocol_sha256':protocol,'assembler_sha256':sha(Path(__file__)),'cases':768,'outputs':{p.name:sha(p) for p in sorted(out.iterdir()) if p.is_file()}})
 print(json.dumps({'packet':str(out/'anonymous-packet.json'),'packet_sha256':sha(out/'anonymous-packet.json'),'subset':str(out/'root-anonymous-subset.json'),'subset_sha256':sha(out/'root-anonymous-subset.json')}))
if __name__=='__main__':main()
