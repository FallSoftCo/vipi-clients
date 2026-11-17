#!/usr/bin/env python3
"""Compile a deliberately non-loadable source-frame-shaped research candidate."""
import hashlib,json,pathlib
D=pathlib.Path(__file__).parent
seed=json.loads((D/'seeds.json').read_text())
utf16=lambda text:len(text.encode('utf-16-le'))//2

def bytes_json(x):return (json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def main():
 out=D/'packs';out.mkdir(exist_ok=True);entries=[]
 for other in ('id','nl','ru'):
  for source,target in (('en',other),(other,'en')):
   patterns=[]
   for c in seed['concepts']:
    word=c['forms'][source];variants=[]
    for context in c['contexts'][source]:
     pos=context.index(word);assert context.count(word)==1
     variants.append({'context':context,'context_scope':'local_phrase','right_boundary':'clause_or_end','focus_utf16':[utf16(context[:pos]),utf16(context[:pos+len(word)])]})
    patterns.append({'id':f'{source}-{target}:{c["id"]}','pair':f'{source}-{target}','concept_id':'prototype:'+c['id'],
     'source':word,'target':c['forms'][target],'reading':c['readings'].get(target,''),'meaning':c['meaning'],
     'source_only_permission':False,'variants':variants})
   pack={'schema':'vipi-source-frame-pack-1','version':f'source-frames-{source}-{target}-001','source':source,'target':target,
    'policy':'reference-first-source-frames-1','approval_sha256':'','runtime_promotion':False,'patterns':patterns}
   data=bytes_json(pack);name=pack['version']+'.json';(out/name).write_bytes(data)
   entries.append({'file':name,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'source':source,'target':target,'patterns':len(patterns),'variants':sum(len(p['variants']) for p in patterns)})
 manifest={'status':'inactive_not_runtime_loadable','reason':'No approval and permissions; native language and reading gates have not been extended or qualified.',
  'seed_sha256':hashlib.sha256((D/'seeds.json').read_bytes()).hexdigest(),'packs':entries}
 (D/'manifest.json').write_bytes(bytes_json(manifest));print('packs',len(entries),'patterns',sum(x['patterns'] for x in entries),'bytes',sum(x['bytes'] for x in entries))
if __name__=='__main__':main()
