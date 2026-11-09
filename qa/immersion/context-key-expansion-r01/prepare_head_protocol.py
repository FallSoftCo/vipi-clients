#!/usr/bin/env python3
"""Local small protocol construction only. No projection, copies or SSH.
Re-running refuses existing private exclusions; new protocol requires review.
"""
import hashlib,json,gzip,unicodedata
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];Q=Path(__file__).resolve().parent
B=Path('/home/ai/Development/investigations');TW=B/'vipi-tatoeba-domain-comparison-20261108-r01';W=B/'vipi-immersion-reconciliation-20261107-r01'
ROOT=Path('/srv/fallsoft/staging/vipi-context-key-expansion-20261109-r01');OLD=Path('/srv/fallsoft/staging/vipi-tatoeba-domain-comparison-20261108-r01')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def write(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2,ensure_ascii=False);f.write('\n')
def main():
 out=B/'vipi-context-key-expansion-20261109-r01/head-preparation-r01';out.mkdir(exist_ok=False)
 base=TW/'exclusions.json';packet=TW/'review-evidence-r01/review-packet.json'
 hashes=set(json.loads(base.read_text())['hashes'])
 for c in json.loads(packet.read_text())['cases']:
  for lang,side in [('en','source'),('es','target')]:
   text=c['full_parallel_record'][side]['text'];norm=' '.join(unicodedata.normalize('NFC',text).casefold().split());hashes.add(hashlib.sha256((lang+'\0'+norm).encode()).hexdigest())
 exclusions=out/'review-exclusions.json';write(exclusions,{'hashes':sorted(hashes),'count':len(hashes),'bindings':{str(p):sha(p) for p in [base,packet]},'scope':'Prior frozen2052 plus full later Tatoeba/PGV32 parallel contexts. Review nomination only; all9535 paired outputs retained. Historical exposure incompletely known.'})
 inputs={}
 def add(name,local,remote=None,known=None,size=None):
  local=Path(local);inputs[name]={'local':str(local),'remote':str(remote or ROOT/'inputs'/local.name),'bytes':size if size is not None else local.stat().st_size,'sha256':known or sha(local)}
 def code(name,relative):add(name,REPO/relative,ROOT/'code'/relative)
 for name,rel in {'phrase_helper':'qa/immersion/corpus-phrase-extraction-r01/extract_phrases.py','normalizer':'qa/immersion/corpus-phrase-extraction-r01/prepare_inputs.py','tokenizer':'qa/immersion/prepare_statistical_alignment_pilot.py','head_helper':'qa/immersion/corpus-phrase-extraction-r01/context_heads.py','lookup_key_dependency':'language-packs/context_hints.py','selector':'qa/immersion/corpus-phrase-extraction-r01/project_native_selection.py','comparator':'qa/immersion/nlp-template-comparison-r01/reference_compare.py','literal_payload':'qa/immersion/nlp-template-comparison-r01/payload.json','literal_semantics':'qa/immersion/nlp-template-comparison-r01/semantics.json','old_projector':'qa/immersion/corpus-phrase-extraction-r01/project_contextual.py','annotation_loader':'qa/immersion/source-role-veto-r01/project.py','content_baseline':'qa/immersion/coverage_ceiling_experiment/content-expansion-candidate-r01.json'}.items():code(name,rel)
 add('dictionary_en',W/'noun-boundary-arms/d-en.sqlite',known='5b16dafff9b2a27474792104bad11195ba8aff2236c134cf0265257b92727d68')
 add('dictionary_es',W/'noun-boundary-arms/d-es.sqlite',known='fcae976ecf9a8eb79c4ea0e4e214e19894db12c8eb21959270e1b9ce78ab1e8e')
 add('family_control',W/'scaled-mechanism-cases-r01/editorial-runtime-candidate-r03.json')
 add('geometry',B/'vipi-android-readiness-20261107-r01/top-down-source-lookup-r01/tokenizer-r87b/rows.jsonl')
 add('annotation_inputs',B/'vipi-source-role-veto-20261108-r01/inputs.json',ROOT/'inputs/annotation-inputs.json')
 add('annotations',B/'vipi-source-role-veto-20261108-r01/android/annotations.jsonl')
 add('source_context',W/'bst-evaluation-source-r01/train.json')
 add('exclusions',exclusions)
 add('matched_keys',B/'vipi-context-key-expansion-20261109-r01/source-inventory-r02/matched-keys.json.gz')
 add('fixed_keys',W/'corpus-phrase-extraction-r01/source-frequency-keys.json',OLD/'inputs/source-frequency-keys.json')
 add('pairs',TW/'remote-evidence/outputs/fetch/en-es-pairs.jsonl.gz',OLD/'outputs/fetch/en-es-pairs.jsonl.gz')
 receipt=json.loads((TW/'fit-evidence-r01/fit-receipt.json').read_text())
 for name,filename in [('forward_align','en-es-forward.align'),('reverse_align','en-es-reverse.align'),('grow_align','en-es-grow-diag-final-and.align'),('forward_params','en-es-forward.params'),('reverse_params','en-es-reverse.params')]:
  b=receipt['outputs'][filename];add(name,TW/'fit-evidence-r01'/filename,OLD/'outputs/fit-r01'/filename,known=b['sha256'],size=b['bytes'])
 receipt=json.loads((Q.parent/'tatoeba-domain-comparison-r01/fit-execution-receipt-r01.json').read_text())['private_receipts']['phrases']['receipt']
 b=receipt['outputs']['candidates.sqlite'];add('fixed_variants',TW/'remote-evidence/outputs/phrases-r01/candidates.sqlite',OLD/'outputs/phrases-r01/candidates.sqlite',known=b['sha256'],size=b['bytes'])
 plan={'schema':'vipi.context-head-comparison.r01','production':False,'status':'pending_root_code_review_no_execution','code_hashes':{n:sha(Q/n) for n in ['head_compare.py','head_review.py']},'inputs':inputs,'stage_quotas_bytes':{s:n*1024**2 for s,n in [('preflight',4),('extract',256),('heads',160),('project',64),('packet',28)]},'limits':{'host':'fallsoft-production-20261106','cpu':1,'nice':10,'address_space_bytes':1024**3,'seconds_per_stage':1200,'output_bytes':512*1024**2,'additional_disk_bytes':int(1.25*1024**3),'free_floor_bytes':8*1024**3},'policy':{'arms':['fixed','expanded'],'key_count':25931,'fixed_source_present':6461,'fixed_original_key_count':8000,'fixed_original_aligned_keys':5816,'same_corpus_pairs':40000,'native_messages':9535,'context_token_max':8,'target_token_max':12,'source_head_unit_max':5,'head_POS':['noun','adj','adv'],'role':'Frozen OpenNLP exact single-token mapped role required, confidence unused, unknown/composites/PROPN abstain','emission':'Single corpus/native/annotation-token content head only; same-face zero output','density':.25,'known':['all_function','all_function_global300'],'representative':'First pair index and source/target token interval insertion order; source/context identity checked','ranking':'distinct components descending, mean bidirectional lexical score descending, variant ID ascending; no alternate rescue','fixed_parity':'Full native-matched existing fixed variant rows and component memberships; absent aligned keys compare empty; no downstream head output until parity complete','proofs':'All phrase variants, all observations, all head alternatives/rejections retained keyed; masks independent; fail on bounds, never truncate','selection':'Exact frozen select; expanded unranked key train_rank1e9; same common candidates, historical strict-containing masks','not_claimed':['all meanings complete','verb coverage','safe grammar transfer','held-out accuracy','catalog activation']},'review':{'seed':'vipi-context-head-expansion-review-r01','ordered_strata':['empty_gain','depth_loss','new_long_context','other_change'],'known':['all_function','all_function_global300'],'quota':4,'maximum':32,'global_unique_source_ids':True,'backfill':False,'depth_loss':'Sum of selected emitted focus native-word costs decreases; context length does not define this stratum, and semantic loss is reviewed separately','output_change':'Focus/target/reading-text sets or mixed output differ; proof identity alone is not change','full_context':True,'independent_labels_before_join':True}}
 codepath=ROOT/'code/qa/immersion/context-key-expansion-r01/head_compare.py'
 plan['commands']=[['timeout','--signal=TERM','--kill-after=10','1210','python3','-B',str(codepath),s] for s in ['preflight','extract','heads','project','packet']]
 write(Q/'head-protocol-r01.json',plan)
 total=sum(x['bytes'] for x in inputs.values() if x['remote'].startswith(str(ROOT)))
 write(out/'preparation-receipt.json',{'complete':True,'corpus_stages_executed':False,'protocol_sha256':sha(Q/'head-protocol-r01.json'),'code_hashes':plan['code_hashes'],'new_input_bytes':total,'output_reservation_bytes':512*1024**2,'total_input_output_bytes':total+512*1024**2,'fits_1_25GiB_envelope':total+512*1024**2<int(1.25*1024**3),'proof_volume_uncertainty':'384269 source occurrences; at most78 permitted target interval expansions each. This loose bound cannot promise completion within512MiB. Stage quotas stop explicitly, retaining all outputs/failure; no truncated success.','remote_metadata_preflight':{'hostname':'fallsoft-production-20261106','free_bytes':290895347712,'retained_fit_files_present':True,'retained_candidates_bytes':41271296,'retained_observations_bytes':16535505,'no_remote_mutations':True}})
 print(json.dumps({'protocol_sha256':sha(Q/'head-protocol-r01.json'),'new_input_bytes':total,'total_with_output':total+512*1024**2,'code_hashes':plan['code_hashes']}))
if __name__=='__main__':main()
