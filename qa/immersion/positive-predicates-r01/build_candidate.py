"""Build a private predicate candidate; production installation is separate."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[3]
W=R.parent/'investigations/vipi-predicate-units-20261109-r01'
sha=lambda b:hashlib.sha256(b).hexdigest()
encode=lambda j:(json.dumps(j,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
base=R/'data/immersion/starter-en-sw-005.json'
assert sha(base.read_bytes())=='c4403e5bb254838a28348d32277c47dcfaa126e7a91a81be6a197ad608b278d7'
policy=json.loads((W/'candidate-policy-r01.json').read_text())
assert sha((W/'candidate-policy-r01.json').read_bytes())=='bf734c87e139bc60877add19ffdd13dea308d112282abad0d95f5968f9ed7c84'
prior=json.loads((R/'qa/immersion/coverage_ceiling_experiment/reviewed-source-clauses-r03.json').read_text())
pack=json.loads(base.read_text()); old=json.loads(base.read_text())['entries'];assert len(old)==213
proof=[]
for entry in prior['entries']:
 source=entry['source']
 if source not in policy['concepts']:continue
 raw=[row for row in prior['attestation']['rows'] if row['word']==entry['evidence_id'] and row['pos']=='verb']
 assert len(raw)==1
 assert any(form['form']==entry['target'] and {'first-person','present','singular'}<=set(form['tags']) for form in raw[0]['exact_target_forms'])
 record={'source':source,'target':entry['target'],'attestation':raw[0],'context_permission':policy['following_contexts'].get(source),'reject_following':policy['reject_following'].get(source,[]),'policy_sha256':sha((W/'candidate-policy-r01.json').read_bytes())}
 digest=sha(encode(record));proof.append({'record_sha256':digest,**record})
 new={'id':entry['id'],'source':source,'source_tokens':source.split(),'target':entry['target'],'reading':None,'reading_kana':None,'category':'content','pos':'finite_predicate','concept_id':policy['concepts'][source],'train_rank':0,'guard':policy['guard'],'record_sha256':digest,'evidence_url':raw[0]['url'],'evidence_scope':'Exact attested first-person present conjugation; authored bounded English source contexts, not complete-clause bilingual attestations.'}
 if source in policy['following_contexts']:new['following_contexts']=policy['following_contexts'][source]
 if source in policy['reject_following']:new['reject_following']=policy['reject_following'][source]
 pack['entries'].append(new)
assert len(pack['entries'])==222 and pack['entries'][:213]==old
pack.update(version='starter-en-sw-006',activation=False,qualification_status='positive_predicate_candidate_not_qualified',positive_predicate_policy={'schema':'vipi-positive-predicate-policy-1','left_operators':policy['left_operators'],'reject_following':policy['global_reject_following']},predicate_parent_sha256=sha(base.read_bytes()),predicate_policy_sha256=sha((W/'candidate-policy-r01.json').read_bytes()))
out=W/'candidate-r01';assert not out.exists();out.mkdir()
data=encode(pack);name='starter-en-sw-006.json';manifest={'schema':'vipi-source-starter-manifest-1','file':name,'sha256':sha(data),'bytes':len(data),'version':pack['version'],'entries':222}
(out/name).write_bytes(data);(out/'starter-sw-catalog.json').write_bytes(encode(manifest));(W/'predicate-provenance-r01.json').write_bytes(encode(proof))
receipt={'candidate_only':True,'base_sha256':sha(base.read_bytes()),'existing_entries_unchanged':213,'new_predicates':9,'new_families':5,'outputs':{p.name:sha(p.read_bytes()) for p in out.iterdir()},'compiler_sha256':sha(Path(__file__).read_bytes())}
(W/'candidate-build-r01.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
