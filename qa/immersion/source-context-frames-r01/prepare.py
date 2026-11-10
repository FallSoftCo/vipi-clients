#!/usr/bin/env python3
"""Prepare original bounded frame evidence, with no source-only permission inferred."""
import json,hashlib,sqlite3,itertools,collections,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[3];W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01')
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(x).hexdigest()
def sha(p):return digest(p.read_bytes())
def expanded(parts):
 states=[('',None)]
 for part in parts:
  assert len(part)==1;k,v=next(iter(part.items()));assert k in ['literal','slot','focus'];choices=v if k=='slot' else [v];assert 1<=len(choices)<=32
  states=[(s+t,(len(s.encode('utf-16-le'))//2,len((s+t).encode('utf-16-le'))//2) if k=='focus' else focus) for s,focus in states for t in choices]
  assert len(states)<=1024
 assert all(x[1] is not None for x in states)
 return [{'context':s,'focus_utf16':list(f)} for s,f in sorted(set(states))]
def main():
 out=W/'preparation-r01';assert not out.exists();out.mkdir();bindings={};summary={};originals=[];all_patterns=[];proofs={}
 for lang,fn in [('ja','starter-en-ja-005.json'),('sw','starter-en-sw-004.json')]:
  db=R/'data/immersion'/('en-'+lang+'.sqlite');active=R/'data/immersion'/fn;bindings[str(db)]=sha(db);bindings[str(active)]=sha(active)
  c=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True);c.execute('pragma query_only=on');rows=c.execute('select id,payload,evidence from mappings order by id').fetchall();groups=collections.defaultdict(list);excluded=[]
  for id,p,e in rows:
   row=json.loads(p);evidence=json.loads(e);assert row['id']==id
   if len(row['source_parts'])==1:excluded.append(id);continue
   assert sum('focus' in x for x in row['source_parts'])==1
   groups[enc(row['source_parts'])].append((row,evidence))
  assert len(groups)==41
  current=json.loads(active.read_text())['entries'];patterns=[]
  for key,records in sorted(groups.items()):
   row=records[0][0];assert len({(x['source'],x['target'],x['reading'],x['meaning']) for x,e in records})==1
   pid='frame-'+digest(('en-'+lang+'\0'+key).encode())[:24];variants=expanded(row['source_parts']);face=row['target'];concepts=sorted({x['concept_id'] for x in current if x['source']==row['source'] and x['target']==face});assert len(concepts)<=1
   refs=[]
   for x,e in records:
    proof={'payload':x,'evidence':e};ph=digest(enc(proof).encode());proofs[ph]=proof;refs.append({'id':x['id'],'record_sha256':x['record_sha256'],'proof_sha256':ph})
    source=e['record']['source_context'];scope=e['record']['source_span'];assert source.encode('utf-16-le')[scope[0]*2:scope[1]*2].decode('utf-16-le')==x['source']
    originals.append({'pair':'en-'+lang,'id':pid+':'+x['id'],'pattern_id':pid,'source':source,'expected_focus_utf16':scope,'original_record_id':x['id'],'exposure':'Retained authored development source; previously stored/reviewed in bidirectional seed evidence. Not fresh held-out text.','stratum':'original_seed_context'})
   patterns.append({'id':pid,'pair':'en-'+lang,'source_parts':row['source_parts'],'source':row['source'],'target':face,'reading':row['reading'],'meaning':row['meaning'],'variants':variants,'original_records':refs,'concept_id':concepts[0] if concepts else 'frame-concept-'+digest(('en-'+lang+'\0'+row['meaning']+'\0'+row['source']+'\0'+face).encode())[:24],'concept_binding':'exact existing source+target face' if concepts else 'new frame-meaning-scoped identifier; no cross-sense/source-only alias inference','source_only_permission':False,'permission_reason':'Original author-assessed bidirectional evidence is not source-only acceptance.'})
  data={'schema':'vipi-source-context-candidate-1','source':'en','target':lang,'runtime_enabled':False,'patterns':patterns};(out/('patterns-en-'+lang+'.json')).write_text(enc(data)+'\n');all_patterns+=patterns
  summary['en-'+lang]={'original_records':sum(len(v) for v in groups.values()),'patterns':len(patterns),'variants':sum(len(p['variants']) for p in patterns),'focus_only_excluded':len(excluded),'excluded_id_sha256':digest(enc(excluded).encode()),'new_concept_ids':sum(p['concept_binding'].startswith('new') for p in patterns)}
 (out/'proofs.json').write_text(enc(proofs)+'\n');(out/'original-source-cases.json').write_text(enc(originals)+'\n')
 readable=['# Bounded source patterns — permission pending','', 'All alternatives are preserved in patterns-en-*.json. Original payloads and assessments remain in proofs.json. Source-only permission is false for every record.','']
 for lang in ['ja','sw']:
  readable+=['## en-'+lang,'','| Pattern | Source focus | Target / reading | Literal/slot source context |','|---|---|---|---|']
  for p in all_patterns:
   if p['pair']=='en-'+lang:readable.append('| '+p['original_records'][0]['id'].split(':')[1]+' | '+p['source']+' | '+p['target']+(' / '+p['reading'] if p['reading'] else '')+' | '+enc(p['source_parts']).replace('|','\\|')+' |')
 (out/'PATTERNS.md').write_text('\n'.join(readable)+'\n')
 receipt={'schema':1,'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),'compiler_sha256':sha(Path(__file__)),'inputs':bindings,'summary':summary,'outputs':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(out.iterdir())},'activation':False,'inference_or_native_execution':False};(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(summary))
if __name__=='__main__':main()
