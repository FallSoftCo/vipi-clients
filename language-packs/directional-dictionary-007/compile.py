#!/usr/bin/env python3
"""Compile only reviewed directions. No network, pivots, runtime edits or activation."""
from pathlib import Path
import json,hashlib,copy,argparse
R=Path(__file__).resolve().parent;I=R/'inputs'
def enc(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()+b'\n'
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_bytes())
def build():
 binding=read(I/'manifest.json')
 for n,h in binding['files'].items():assert sha((I/n).read_bytes())==h,n
 rows=read(I/'reviewed-mappings.json')['rows'];out={};pairs={};summary=[]
 amendments=read(I/'approved-italian-amendment.json')['changes']
 for r in rows:pairs.setdefault(r['pair'],[]).append(r)
 for c in amendments:pairs.setdefault(c['pair'],[])
 index=read(I/'base/all-pair-source-catalog-001.json')
 for pair,rs in sorted(pairs.items()):
  manifest=read(I/'base'/f'source-frames-{pair}-catalog.json');base=read(I/'base'/manifest['file']);patterns=copy.deepcopy(base['patterns'])
  changes=[c for c in amendments if c['pair']==pair]
  for c in changes:
   assert sha((I/'base'/c['base_pack_file']).read_bytes())==c['base_pack_sha256']
   p=next(p for p in patterns if p['id']==c['pattern_id']);assert p==c['before'];p['variants']=copy.deepcopy(c['proposed_variants'])
  for r in rs:
   assert r['source_review']=='accept' and r['target_review']=='accept'
   p={k:r[k] for k in ['id','pair','source','target','reading','meaning','concept_id','variants']}
   p.update(source_only_permission=True,dictionary_provenance={'license_id':'CC-BY-SA-4.0','mapping_file':'reviewed-mappings.json','mapping_sha256':binding['files']['reviewed-mappings.json'],'owner_proposal_id':r['owner_proposal_id'],'no_reverse_or_pivot_permission':True})
   assert len(p['variants'])<=1024
   for v in p['variants']:
    a,b=v['focus_utf16'];assert 0<=a<b<=len(v['context'].encode('utf-16-le'))//2<=256;assert v['context'].encode('utf-16-le')[a*2:b*2].decode('utf-16-le')==p['source']
   if base['target'] in ['ar','zh','ja','ko']:assert p['reading']
   patterns.append(p)

  for before,after in zip(base['patterns'],patterns):
   expected=copy.deepcopy(before)
   c=next((c for c in changes if c['pattern_id']==before['id']),None)
   if c:expected['variants']=c['proposed_variants']
   assert after==expected
  for p in patterns:
   assert len(p['variants'])<=1024
   for v in p['variants']:
    a,b=v['focus_utf16'];assert 0<=a<b<=len(v['context'].encode('utf-16-le'))//2<=256;assert v['context'].encode('utf-16-le')[a*2:b*2].decode('utf-16-le')==p['source']
  assert len(patterns)<=256;assert len({p['id'] for p in patterns})==len(patterns)
  version=f'source-frames-{pair}-007';filename=version+'.json';pack={**base,'version':version,'patterns':patterns,'runtime_promotion':False,'parent_pack_sha256':manifest['sha256'],'dictionary_increment_input_sha256':sha((I/'manifest.json').read_bytes())};body=enc(pack);assert len(body)<=1048576
  m={**manifest,'file':filename,'version':version,'patterns':len(patterns),'sha256':sha(body),'bytes':len(body)};mb=enc(m);assert len(mb)<=8192
  out['packs/'+filename]=body;out[f'packs/source-frames-{pair}-catalog.json']=mb;summary.append({'pair':pair,'retained':len(base['patterns']),'constrained_variants':len(changes),'unchanged_rows':len(base['patterns'])-len(changes),'added':len(rs),'total':len(patterns),'bytes':len(body)})
  if pair not in ['en-ja','en-sw']:
   entry=next(e for e in index['entries'] if e['pair']==pair);entry.update(file=filename,sha256=sha(body),bytes=len(body),manifest_file=f'source-frames-{pair}-catalog.json',manifest_sha256=sha(mb),manifest_bytes=len(mb))
 out['packs/all-pair-source-catalog-001.json']=enc(index)
 out['native-fixtures.json']=enc(read(I/'focused-fixtures.json'))
 out['review-manifest.json']=enc({'schema':'vipi-directional-dictionary-review-1','runtime_promotion':False,'root_activation_approved':False,'source_permission_scope':'Root-approved finite combined private candidate only; no production selection.','italian_rows_constrained':len(amendments),'license_id':'CC-BY-SA-4.0','input_manifest_sha256':sha((I/'manifest.json').read_bytes()),'pairs':summary})
 out['hash-manifest.json']=enc({'runtime_promotion':False,'compiler_sha256':sha(Path(__file__).read_bytes()),'files':{n:{'sha256':sha(b),'bytes':len(b)} for n,b in sorted(out.items())}})
 return out
if __name__=='__main__':
 p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--verify',type=Path);a=p.parse_args();out=build()
 if a.output:
  assert not a.output.exists();a.output.mkdir()
  for n,b in out.items():q=a.output/n;q.parent.mkdir(exist_ok=True);q.write_bytes(b)
 else:
  for n,b in out.items():assert (a.verify/n).read_bytes()==b,n
 print(json.dumps({'files':len(out),'bytes':sum(map(len,out.values())),'manifest_sha256':sha(out['hash-manifest.json'])}))
