#!/usr/bin/env python3
"""Audit the observed-output qualification subset against frozen primary-backed inventory."""
import collections,hashlib,json
from pathlib import Path
Q=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 pack=json.loads((Q/'reviewed-source-unit-native-candidate-r03.json').read_text());rows=[];pairs={};inputs={'reviewed-source-unit-native-candidate-r03.json':sha(Q/'reviewed-source-unit-native-candidate-r03.json'),'prepare_source_unit_candidate.py':sha(Q/'prepare_source_unit_candidate.py')}
 for lang in ['sw','ja','es']:
  wordfile='reviewed-word-lexicon-en-sw-r02.json' if lang=='sw' else f'reviewed-word-lexicon-en-{lang}-transfer-r01.json';rulefile='source-question-rules-r02.json' if lang=='sw' else f'source-question-rules-en-{lang}-transfer-r01.json';lex=json.loads((Q/wordfile).read_text());rules=json.loads((Q/rulefile).read_text());inputs[wordfile]=sha(Q/wordfile);inputs[rulefile]=sha(Q/rulefile);p=pack['pairs']['en-'+lang]
  inventory={e['id']:dict(e,kind='word') for e in lex['entries']}
  for source,r in {**rules['single_words'],**rules['units']}.items():
   sid=f'question-en-{lang}-'+source.replace(' ','-');inventory[sid]=dict(r,id=sid,source=source,kind='question',category='function',concept_id='question:'+source,train_rank=16)
  statuses={e['id']:'retained_starter' for e in p['entries']};statuses.update({x:'unexercised_only' for x in p['withheld_unexercised']});statuses.update({x['id']:'observed_unresolved_sense_or_scope' for x in p['excluded_unresolved']});statuses.update({x:'unchanged_written_face' for x in p['excluded_unchanged_faces']});statuses.update({x['entry']['id']:'explicit_target_scope_withholding' for x in p.get('withheld_target_scope',[])})
  assert set(statuses)==set(inventory),(lang,set(inventory)-set(statuses))
  rr=[]
  for sid,e in inventory.items():
   rr.append({'id':sid,'source':e['source'],'target':e['target'],'kind':e['kind'],'category':e['category'],'concept_id':e.get('concept_id',e['source']),'status':statuses[sid],'train_rank':e.get('train_rank'),'train_occurrences':e.get('train_occurrences'),'dictionary_or_authored_evidence_present':bool(e.get('evidence')),'reading_present':bool(e.get('reading')) if lang=='ja' else None,'source_guard':e.get('guard'),'meaning_qualification':'Existing frozen primary spelling/sense evidence is lexical evidence; absent selected-context review is not a demonstrated failure.' if statuses[sid]=='unexercised_only' else 'See bound existing observations/audits.'})
  by_status={}
  for status in sorted(set(statuses.values())):
   ss=[r for r in rr if r['status']==status];by_status[status]={'forms':len(ss),'words':sum(r['kind']=='word' for r in ss),'questions':sum(r['kind']=='question' for r in ss),'content_forms':sum(r['category']=='content' for r in ss),'function_forms':sum(r['category']=='function' for r in ss),'distinct_concept_ids':len(set(r['concept_id'] for r in ss)),'word_forms_with_primary_evidence':sum(r['kind']=='word' and r['dictionary_or_authored_evidence_present'] for r in ss),'japanese_forms_with_reading':sum(bool(r['reading_present']) for r in ss) if lang=='ja' else None}
  unavailable=[]
  for x in p['target_unavailable']:
   src=x['source'];reason=x['reason'];cause='unresolved_sense_or_valency'
   if any(w in reason for w in ['gender','case/preposition','agreement','sibling relative age']):cause='target_form_or_agreement_policy'
   if any(w in reason for w in ['bound prefix','particles carry','coordination']):cause='free_word_scope_or_bound_construction'
   unavailable.append(dict(x,audit_class=cause))
  pairs[lang]={'available_word_forms':len(lex['entries']),'available_question_units':len(inventory)-len(lex['entries']),'source_forms_without_selected_target':len(unavailable),'unavailable_classes':dict(collections.Counter(x['audit_class'] for x in unavailable)),'by_status':by_status,'top_train_rank_unexercised_content':[r for r in sorted(rr,key=lambda r:(r['train_rank'] or 9999,r['id'])) if r['status']=='unexercised_only' and r['category']=='content'][:20],'entries':rr,'target_unavailable':unavailable}
 out={'production':False,'fresh_holdout':False,'inputs':inputs,'finding':'The starter is a post-evaluation observed-unit qualification subset. It intentionally omits never-selected primary-backed forms; this is an observation-dependent native QA boundary, not a scalable semantic admission policy or dictionary availability ceiling.','source_code':'prepare_source_unit_candidate.py lines95-102 requires at least one prior selected observation. No dictionary lookup/index limitation causes this omission.','pairs':pairs,'limits':['Unexercised is neither incorrect nor production-qualified; primary attestation does not prove contextual safety.','Unavailable target forms include deliberately conservative grammatical policy decisions, not only unknown meanings.','No target data, source guard, matcher or app setting changed by this audit.']}
 f=Q/'source-starter-inventory-audit-r01.json';assert not f.exists();f.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(sha(f))
 for l,p in pairs.items():print(l,p['available_word_forms'],p['available_question_units'],p['source_forms_without_selected_target'],p['unavailable_classes']);print(json.dumps(p['by_status'],ensure_ascii=False))
if __name__=='__main__':main()
