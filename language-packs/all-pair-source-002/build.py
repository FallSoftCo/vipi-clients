#!/usr/bin/env python3
"""Compile pinned finite source-frame assets; never activates native providers.

Inputs live beside this file. --output requires a new directory; --verify reads
an existing asset directory without changing it. Exactly 108 new directions
are emitted; existing en-ja/en-sw assets/providers are excluded.
"""
import argparse, hashlib, itertools, json
from pathlib import Path

HERE=Path(__file__).resolve().parent
EXCLUDED={'en-ja','en-sw'}
LANGUAGES={'en','es','fr','de','pt','it','ar','zh','ja','ko','sw'}
def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()+b'\n'
def sha(value):return hashlib.sha256(value).hexdigest()
def u16(value):return len(value.encode('utf-16-le'))//2
def assets():
 grid=json.loads((HERE/'concept-grid.json').read_bytes());review_bytes=(HERE/'review-manifest.json').read_bytes();review=json.loads(review_bytes)
 assert grid['schema']=='vipi-common-concept-grid-candidate-2'
 assert review['runtime_promotion'] is False
 assert grid['review_sha256']==sha(review_bytes)
 concepts=grid['concepts'];bykey={c['key']:c for c in concepts}
 assert len(bykey)==len(concepts)==42
 for c in concepts:assert set(c['languages'])==LANGUAGES
 withheld={(x['language'],x['key']) for x in grid['standalone_withheld_sources']}
 result={};index=[]
 for source,target in itertools.permutations(sorted(LANGUAGES),2):
  pair=source+'-'+target
  if pair in EXCLUDED:continue
  patterns=[]
  def make(c,standalone=False):
   a,b=c['languages'][source],c['languages'][target]
   variants=[{'context':a['focus'],'focus_utf16':[0,u16(a['focus'])],'context_scope':'local_phrase'}] if standalone else a['variants']
   assert 0<len(variants)<=1024
   if target in {'ar','zh','ja','ko'}:assert b['reading']
   for v in variants:
    lo,hi=v['focus_utf16'];assert 0<=lo<hi<=u16(v['context'])<=256
    assert v['context'].encode('utf-16-le')[2*lo:2*hi].decode('utf-16-le')==a['focus']
    assert v['context_scope'] in {'local_phrase','whole_sentence'}
    assert v.get('right_boundary') in {None,'clause_or_end'}
   return {'id':pair+':'+('standalone:' if standalone else '')+c['key'],'pair':pair,'source':a['focus'],'target':b['focus'],'reading':b['reading'],'meaning':c['meaning'],'concept_id':c['id'],'source_only_permission':True,'variants':variants,'original_records':[{'id':a['retained_record_id'],'record_sha256':a['record_sha256'],'proof_sha256':a['evidence_sha256']},{'id':b['retained_record_id'],'record_sha256':b['record_sha256'],'proof_sha256':b['evidence_sha256']}]}
  patterns.extend(make(c) for c in concepts)
  patterns.extend(make(bykey[key],True) for key in grid['standalone_groups'] if (source,key) not in withheld)
  assert len(patterns)<=256 and len({p['id'] for p in patterns})==len(patterns)
  version='source-frames-'+pair+'-002';filename=version+'.json'
  pack={'schema':'vipi-source-frame-pack-1','version':version,'source':source,'target':target,'policy':'reference-first-source-frames-1','approval_sha256':sha(review_bytes),'patterns':patterns}
  body=encode(pack);assert len(body)<=1_048_576
  manifest={'schema':'vipi-source-frame-manifest-1','file':filename,'sha256':sha(body),'bytes':len(body),'patterns':len(patterns),'version':version,'source':source,'target':target,'policy':pack['policy']}
  manifest_name='source-frames-'+pair+'-catalog.json';manifest_body=encode(manifest);assert len(manifest_body)<=8192
  result[filename]=body;result[manifest_name]=manifest_body
  index.append({'pair':pair,'source':source,'target':target,'file':filename,'sha256':sha(body),'bytes':len(body),'manifest_file':manifest_name,'manifest_sha256':sha(manifest_body),'manifest_bytes':len(manifest_body)})
 assert len(index)==108 and not EXCLUDED.intersection(x['pair'] for x in index)
 result['all-pair-source-catalog-001.json']=encode({'schema':'vipi-bundled-source-frame-index-1','entries':index})
 return result
def main():
 parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
 mode.add_argument('--output',type=Path);mode.add_argument('--verify',type=Path);args=parser.parse_args();expected=assets()
 if args.output:
  assert not args.output.exists(),'Use a new output directory; do not overwrite active assets.'
  args.output.mkdir(parents=True)
  for name,body in expected.items():(args.output/name).write_bytes(body)
 else:
  for name,body in expected.items():assert (args.verify/name).read_bytes()==body,name+' differs'
 index=expected['all-pair-source-catalog-001.json']
 print(json.dumps({'files':len(expected),'new_directions':108,'excluded_pairs':sorted(EXCLUDED),'index_sha256':sha(index),'index_bytes':len(index),'runtime_activation':False,'mode':'write_new_directory' if args.output else 'read_only_verify'},sort_keys=True))
if __name__=='__main__':main()
