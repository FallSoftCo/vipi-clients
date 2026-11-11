from pathlib import Path
import json,hashlib,copy,argparse,itertools
R=Path(__file__).resolve().parent;I=R/'inputs'
def enc(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()+b'\n'
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_bytes())
def build():
 binding=read(I/'input-manifest.json')
 for p,h in binding['input_sha256'].items():assert sha((I/p).read_bytes())==h,p
 scope=read(I/'scope.json');langs=['en','es','fr','de','it','pt','ar','zh','ja','ko','sw'];packs={};manifests={}
 for a,b in itertools.permutations(langs,2):
  pair=a+'-'+b;m=read(I/'base'/f'source-frames-{pair}-catalog.json');manifests[pair]=m;packs[pair]=read(I/'base'/m['file'])
 approval={'schema':'vipi-bare-noun-private-review-1','runtime_promotion':False,'experiment_only':False,'input_manifest_sha256':sha((I/'input-manifest.json').read_bytes()),'parent_export_hash_manifest_sha256':binding['parent_export_hash_manifest_sha256'],'scope_sha256':binding['input_sha256']['scope.json'],'approval':'Root reviewed finite content and requested this packaging proposal; activation remains separately pending.'};out={'review-manifest.json':enc(approval)};ash=sha(out['review-manifest.json']);index=[];summary=[];added={};target_fallback=[]
 for pair,base in packs.items():
  source,target=pair.split('-');patterns=copy.deepcopy(base['patterns']);old=len(patterns)
  for row in scope['accepted']:
   if row['language']!=source:continue
   cid=row['concept_id'];found=[p for p in patterns[:old] if p['concept_id']==cid]
   if not found:
    found=[p for k,v in packs.items() if k.endswith('-'+target) for p in v['patterns'] if p['concept_id']==cid]
    target_fallback.append({'pair':pair,'concept_id':cid,'basis':'Same retained common concept accepted in other source→this target pack; en-ja/sw baseline has different concept IDs.'})
   assert found,(pair,cid)
   faces={(p['target'],p['reading']) for p in found};assert len(faces)==1,(pair,cid,faces)
   face,reading=next(iter(faces));ident='bare-noun-r01:'+pair+':'+cid.split(':')[-1]
   p={'id':ident,'pair':pair,'source':row['source'],'target':face,'reading':reading,'meaning':found[0]['meaning'],'concept_id':cid,'source_only_permission':True,'variants':copy.deepcopy(row['proposed_variants']),'editorial_provenance':{'kind':'root_reviewed_finite_bare_noun_packaging_proposal','scope_sha256':binding['input_sha256']['scope.json'],'source_review_only_no_new_target_translation':True,'target_parent_pattern_id':found[0]['id'],'parent_export_hash_manifest_sha256':binding['parent_export_hash_manifest_sha256'],'review_manifest_sha256':ash}}
   if target in ['ar','zh','ja','ko']:assert reading
   for v in p['variants']:
    a,b=v['focus_utf16'];assert v['context'].encode('utf-16-le')[2*a:2*b].decode('utf-16-le')==p['source'];assert b<=256
   patterns.append(p);added[(pair,row['source'])]=p
  assert patterns[:old]==base['patterns'];assert len(patterns)<=256;assert len({p['id'] for p in patterns})==len(patterns)
  version='source-frames-'+pair+'-005';filename=version+'.json';pack={**base,'version':version,'patterns':patterns,'approval_sha256':ash,'runtime_promotion':False,'parent_pack_sha256':manifests[pair]['sha256']};body=enc(pack);assert len(body)<=1048576
  manifest={**manifests[pair],'file':filename,'version':version,'sha256':sha(body),'bytes':len(body),'patterns':len(patterns)};mn='source-frames-'+pair+'-catalog.json';mb=enc(manifest);out['packs/'+filename]=body;out['packs/'+mn]=mb
  if pair not in ['en-ja','en-sw']:index.append({'pair':pair,'source':source,'target':target,'file':filename,'sha256':sha(body),'bytes':len(body),'manifest_file':mn,'manifest_sha256':sha(mb),'manifest_bytes':len(mb)})
  summary.append({'pair':pair,'preserved_patterns':old,'added_patterns':len(patterns)-old,'total_patterns':len(patterns),'bytes':len(body)})
 inp=read(I/'chat-inputs.json');cases=[];controls=[]
 for n,(lang,text,word) in enumerate(inp['positives']):
  target='es' if lang=='en' else 'en';pair=lang+'-'+target;p=added[(pair,word)];i=text.index(word);start=len(text[:i].encode('utf-16-le'))//2
  cases.append({'id':f'bare-chat-{n:02}','pair':pair,'source_language':lang,'target_language':target,'original':text,'pattern_id':p['id'],'concept_id':p['concept_id'],'expected_source':word,'expected_target':p['target'],'reading':p['reading'],'focus_utf16':[start,start+len(word.encode('utf-16-le'))//2],'density':0.5,'composed_density':0.25,'kind':'new_authored_chat_not_heldout','expectation':'Opportunity only; preserve detector/native/density abstentions.'})
 for n,(lang,text,word,reason) in enumerate(inp['negatives']):
  target='es' if lang=='en' else 'en';controls.append({'id':f'bare-negative-{n:02}','pair':lang+'-'+target,'source_language':lang,'target_language':target,'original':text,'forbidden_focus':word,'forbidden_pattern_prefix':'bare-noun-r01:','expected_no_spans':False,'reason':reason,'assertion':'No added pilot output for the named focus; independently retained patterns may still emit.'})
 out['native-fixtures.json']=enc({'schema':'vipi-editorial-extension-native-fixtures-1','runtime_promotion':False,'cases':cases,'controls':controls,'frozen_benchmark_unchanged':True,'scope':'19 retained authored chats and27 ambiguity controls; no new broad test suite.'})
 out['packs/all-pair-source-catalog-001.json']=enc({'schema':'vipi-bundled-source-frame-index-1','entries':index})
 out['differential-summary.json']=enc({'runtime_promotion':False,'parent_export_hash_manifest_sha256':binding['parent_export_hash_manifest_sha256'],'pairs':summary,'existing_rows_identically_preserved':True,'existing_targets_and_readings_identical':True,'accepted_source_faces':len(scope['accepted']),'excluded_source_faces':len(scope['excluded']),'patterns_appended':sum(r['added_patterns'] for r in summary),'target_metadata_reused_across_existing_common_concept':target_fallback,'native_qualified':False})
 out['hash-manifest.json']=enc({'schema':'vipi-private-candidate-file-hashes-1','runtime_promotion':False,'compiler_sha256':sha(Path(__file__).read_bytes()),'input_manifest_sha256':sha((I/'input-manifest.json').read_bytes()),'files':{n:{'sha256':sha(b),'bytes':len(b)} for n,b in sorted(out.items())}})
 return out
if __name__=='__main__':
 p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--verify',type=Path);args=p.parse_args();out=build()
 if args.output:
  assert not args.output.exists();args.output.mkdir()
  for n,b in out.items():q=args.output/n;q.parent.mkdir(exist_ok=True);q.write_bytes(b)
 else:
  for n,b in out.items():assert (args.verify/n).read_bytes()==b,n
 print(json.dumps({'files':len(out),'bytes':sum(map(len,out.values())),'hash_manifest_sha256':sha(out['hash-manifest.json']),'fixtures_sha256':sha(out['native-fixtures.json']),'index_sha256':sha(out['packs/all-pair-source-catalog-001.json'])}))
