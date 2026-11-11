#!/usr/bin/env python3
"""Private deterministic candidate compiler. No canonical writes or native activation."""
import argparse,copy,hashlib,itertools,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent;I=ROOT/'inputs'
def encode(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()+b'\n'
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_bytes())
def u16(s):return len(s.encode('utf-16-le'))//2
LANGS=['en','es','fr','de','it','pt','ar','zh','ja','ko','sw']
PREFIX={'en':'We can talk about this later. ','es':'Podemos hablar de esto más tarde. ','fr':'Nous pouvons en parler plus tard. ','de':'Wir können später darüber sprechen. ','it':'Possiamo parlarne più tardi. ','pt':'Podemos falar sobre isso mais tarde. ','ar':'يمكننا التحدث عن هذا لاحقًا. ','zh':'我们可以稍后再谈这件事。','ja':'この話は後でしましょう。','ko':'이 이야기는 나중에 다시 해요. ','sw':'Tunaweza kuzungumza kuhusu hili baadaye. '}
def build():
 binding=read(I/'input-manifest.json')
 for name,digest in binding['input_sha256'].items():assert sha((I/name).read_bytes())==digest,name
 target_overrides=read(I/'target-overrides.json')['rows']
 grids=[(name,read(I/name)) for name in ['everyday-amended-grid.json','frequency-amended-grid.json']]
 aliases=read(I/'colloquial-amended-supplement.json')['entries'];concepts={c['key']:c for _,g in grids for c in g['concepts']};assert len(concepts)==82
 approval={'schema':'vipi-finite-editorial-candidate-approval-1','runtime_promotion':False,'canonical_base_revision':binding['canonical_base_revision'],'input_manifest_sha256':sha((I/'input-manifest.json').read_bytes()),'root_acceptance':binding['permission'],'review_level':binding['provenance'],'runtime_note':'True permissions below authorize only root-accepted finite content in this private test export. No shipped catalog/flag changes.'}
 output={'review-manifest.json':encode(approval)};approvalsha=sha(output['review-manifest.json']);index=[];pairsummary=[];cases=[];controls=[];overlaps=[]
 for source,target in itertools.permutations(LANGS,2):
  pair=f'{source}-{target}';bm=read(I/'base'/f'source-frames-{pair}-catalog.json');base=read(I/'base'/bm['file']);patterns=copy.deepcopy(base['patterns']);oldcount=len(patterns);assert all(p['source_only_permission'] for p in patterns)
  def append(c,sv,tv,gridname,aliasid=None):
   assert sv['source_review']=='accept' and tv['target_review']=='accept'
   ident=f'editorial-003:{pair}:{c["key"]}'+(':'+aliasid if aliasid else '')
   p={'id':ident,'pair':pair,'source':sv['focus'],'target':tv['focus'],'reading':tv['reading'],'meaning':c['meaning'],'concept_id':c['id'],'source_only_permission':True,'variants':copy.deepcopy(sv['variants']),'editorial_provenance':{'kind':'original_agent_authored_root_reviewed_candidate','grid_file':gridname,'grid_sha256':binding['input_sha256'][gridname],'target_grid_file':('frequency-amended-grid.json' if aliasid else gridname),'target_grid_sha256':binding['input_sha256']['frequency-amended-grid.json' if aliasid else gridname],'source_cell_sha256':sha(encode(sv)),'target_cell_sha256':sha(encode(tv)),'review_manifest_sha256':approvalsha}}
   p['editorial_provenance']['reading_amendment_sha256']=binding['input_sha256']['reading-amendment.json']
   if target=='ar':p['editorial_provenance']['arabic_compatibility_amendment_sha256']=binding['input_sha256']['arabic-compatibility-amendment.json']
   if source=='en' and c['key'] in ['again','later']:
    p['editorial_provenance']['source_scope_amendment_sha256']=binding['input_sha256']['source-scope-amendment.json']
   override=next((r for r in target_overrides if r['concept_id']==c['id'] and r['target_language']==target),None)
   if override:
    assert tv['focus']==override['source_face_unchanged']
    p['target']=override['target_face'];p['reading']=override['reading']
    p['editorial_provenance']['target_override_sha256']=binding['input_sha256']['target-overrides.json']
   assert 0<len(p['variants'])<=1024
   for v in p['variants']:
    a,b=v['focus_utf16'];assert 0<=a<b<=u16(v['context'])<=256
    assert v['context'].encode('utf-16-le')[2*a:2*b].decode('utf-16-le')==p['source']
    assert v['context_scope'] in ['local_phrase','whole_sentence'] and v.get('right_boundary') in [None,'clause_or_end']
   if target in ['ar','zh','ja','ko']:assert p['reading']
   existing=[x['id'] for x in base['patterns'] if x['source']==p['source']]
   if existing:overlaps.append({'pair':pair,'new_id':ident,'source':p['source'],'existing_ids':existing})
   patterns.append(p)
   for j,v in enumerate(p['variants']):
    original=PREFIX[source]+v['context'];start=u16(PREFIX[source])+v['focus_utf16'][0];end=u16(PREFIX[source])+v['focus_utf16'][1]
    cases.append({'id':ident+f':v{j}','pair':pair,'source_language':source,'target_language':target,'original':original,'concept_id':p['concept_id'],'pattern_id':ident,'expected_source':p['source'],'expected_target':p['target'],'reading':p['reading'],'focus_utf16':[start,end],'kind':'authored_candidate_probe_not_heldout','density':0.5,'composed_density':0.25,'expectation':'Candidate semantic opportunity, not mandatory output: preserve native boundary/density/detector abstentions.'})
  for name,grid in grids:
   for c in grid['concepts']:
    sv,tv=c['languages'][source],c['languages'][target]
    if sv['source_review']=='accept' and tv['target_review']=='accept':append(c,sv,tv,name)
  for n,sv in enumerate(aliases):
   if sv['language']==source and sv['source_review']=='accept':
    c=concepts[sv['concept']];tv=c['languages'][target]
    if tv['target_review']=='accept':append(c,sv,tv,'colloquial-amended-supplement.json',f'alias{n}')
  assert patterns[:oldcount]==base['patterns'];assert len(patterns)<=256;assert len({p['id'] for p in patterns})==len(patterns)
  version=f'source-frames-{pair}-003';name=version+'.json';pack={**base,'patterns':patterns,'version':version,'approval_sha256':approvalsha,'base_pack_sha256':bm['sha256'],'base_approval_sha256':base['approval_sha256'],'runtime_promotion':False}
  body=encode(pack);assert len(body)<=1048576
  manifest={'schema':'vipi-source-frame-manifest-1','file':name,'sha256':sha(body),'bytes':len(body),'patterns':len(patterns),'version':version,'source':source,'target':target,'policy':base['policy']};mn=f'source-frames-{pair}-catalog.json';mb=encode(manifest);assert len(mb)<=8192
  output['packs/'+name]=body;output['packs/'+mn]=mb
  if pair not in ['en-ja','en-sw']:index.append({'pair':pair,'source':source,'target':target,'file':name,'sha256':sha(body),'bytes':len(body),'manifest_file':mn,'manifest_sha256':sha(mb),'manifest_bytes':len(mb)})
  pairsummary.append({'pair':pair,'base_patterns_preserved':oldcount,'added_patterns':len(patterns)-oldcount,'total_patterns':len(patterns),'bytes':len(body)})
 for probe in read(I/'semantic-controls.json')['controls']:
  for target in LANGS:
   source=probe['source_language']
   if target==source:continue
   c=concepts[probe['concept']]
   controls.append({**probe,'id':probe['id']+':'+source+'-'+target,'pair':source+'-'+target,'target_language':target,'forbidden_concept_id':c['id'],'forbidden_pattern_prefix':f'editorial-003:{source}-{target}:{c["key"]}','expected_no_spans':False,'assertion':'No output attributed to this new concept/focus. Independent accepted concepts and preserved baseline outputs are allowed.'})
 assert len(index)==108
 output['packs/all-pair-source-catalog-001.json']=encode({'schema':'vipi-bundled-source-frame-index-1','entries':index})
 output['native-fixtures.json']=encode({'schema':'vipi-editorial-extension-native-fixtures-1','runtime_promotion':False,'cases':cases,'controls':controls,'prefixes':PREFIX,'case_policy':'Exact reviewed finite contexts; English again/later verb phrases include explicit uppercase-first-character copies. No global casefold or morphology exceptions.'})
 output['structural-receipt.json']=encode({'runtime_promotion':False,'canonical_base_revision':binding['canonical_base_revision'],'pairs':pairsummary,'pair_count':110,'index_pairs':108,'authored_positive_probes':len(cases),'concept_specific_negative_probes':len(controls),'all_existing_rows_preserved':True,'same_source_baseline_overlaps':overlaps,'native_qualification':False,'frozen_evaluation_sha256':binding['frozen_evaluation_readonly_sha256']})
 output['hash-manifest.json']=encode({'schema':'vipi-private-candidate-file-hashes-1','runtime_promotion':False,'input_manifest_sha256':sha((I/'input-manifest.json').read_bytes()),'compiler_sha256':sha(Path(__file__).read_bytes()),'files':{name:{'sha256':sha(body),'bytes':len(body)} for name,body in sorted(output.items())}})
 return output
if __name__=='__main__':
 p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--output',type=Path);g.add_argument('--verify',type=Path);a=p.parse_args();files=build()
 if a.output:
  assert not a.output.exists(),'Require new output directory';a.output.mkdir(parents=True)
  for name,body in files.items():q=a.output/name;q.parent.mkdir(exist_ok=True);q.write_bytes(body)
 else:
  for name,body in files.items():assert (a.verify/name).read_bytes()==body,name
 print(json.dumps({'files':len(files),'total_bytes':sum(map(len,files.values())),'index_sha256':sha(files['packs/all-pair-source-catalog-001.json']),'fixtures_sha256':sha(files['native-fixtures.json']),'mode':'write' if a.output else 'read_only_verify'}))
