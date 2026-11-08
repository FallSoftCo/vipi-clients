#!/usr/bin/env python3
"""TRAIN-derived lexical-evidence candidate; prior selection is not an admission rule."""
import argparse,copy,hashlib,json
from pathlib import Path
Q=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();base=json.loads((Q/'reviewed-source-unit-native-candidate-r03.json').read_text());candidate=copy.deepcopy(base);inputs={'reviewed-source-unit-native-candidate-r03.json':sha(Q/'reviewed-source-unit-native-candidate-r03.json')};summaries={};exclusions=[]
 globallex=json.loads((Q/'reviewed-word-lexicon-en-sw-r02.json').read_text());concepts={}
 for e in globallex['entries']:
  if e['category']=='content':concepts[e['concept_id']]=min(concepts.get(e['concept_id'],99999),e['train_rank'])
 learned=[k for k,v in sorted(concepts.items(),key=lambda t:(t[1],t[0]))]
 for l,pair in candidate['pairs'].items():
  lang=l.split('-')[1];name='reviewed-word-lexicon-en-sw-r02.json' if lang=='sw' else f'reviewed-word-lexicon-en-{lang}-transfer-r01.json';inputs[name]=sha(Q/name);lex=json.loads((Q/name).read_text());byid={e['id']:e for e in lex['entries']};existing={e['id'] for e in pair['entries']};add=[]
  for e in pair['entries']:
   original=byid.get(e['id']);e['concept_id']=original['concept_id'] if original else 'question:'+e['source'];e['evidence_state']='previously_observed_qualification';e['primary_evidence']=original.get('evidence') if original else e.get('provenance',e.get('evidence'))
  for sid in pair['withheld_unexercised']:
   e=byid.get(sid)
   if not e or e['category']!='content':continue
   if lang=='ja' and e['concept_id']=='month':
    exclusions.append({'id':sid,'reason':'Same month/months duration-vs-calendar sense and reading family as the existing explicit months withholding. No new target or context-specific patch added.','audit_sha256':sha(Q/'japanese-month-scope-audit-r02.json')});continue
   assert e.get('evidence'),sid
   if lang=='ja':assert e.get('reading') and e.get('reading_kana'),sid
   addition=copy.deepcopy(e);addition['source_tokens']=e['source'].split();addition['evidence_state']='lexical_attestation_before_new_holdout_not_previously_selected';addition['primary_evidence']=addition.pop('evidence');add.append(addition)
  pair['entries']+=sorted(add,key=lambda e:(e['train_rank'],e['id']))
  pair['prior_qualification_summary']=pair.pop('summary');pair['prior_withheld_unexercised']=pair['withheld_unexercised'];pair['withheld_unexercised']=[sid for sid in pair['withheld_unexercised'] if sid not in {e['id'] for e in add}]
  pair['summary']={'research_units':len(pair['entries']),'content_forms':sum(e['category']=='content' for e in pair['entries']),'prior_observed_units':len(existing),'lexically_attested_unobserved_content_additions':len(add)}
  summaries[l]={'old_units':len(existing),'added_content_forms':len(add),'result_units':len(pair['entries']),'content_forms':sum(e['category']=='content' for e in pair['entries']),'distinct_content_concepts':len({e['concept_id'] for e in pair['entries'] if e['category']=='content'}),'added_concepts':len({e['concept_id'] for e in add})}
 candidate.update(schema='vipi-content-expansion-research-1',production=False,status='Research only. TRAIN-derived primary-attested content expansion, not enabled in native apps.',selection_basis='Retain starter units; add every primary-attested TRAIN content form withheld solely for never being previously selected. Keep unresolved/unchanged/target-unavailable exclusions and explicit family exclusion.',pack_version='content-expansion-research-r01',inputs=inputs,expansion_summary=summaries,additional_family_exclusions=exclusions,learned_content_global_train_order=learned,compiler_sha256=sha(Path(__file__)))
 candidate['runtime_contract']=dict(production=False,source_eligibility='Unchanged evaluate_source_concepts guards, primary matcher protections, complete source ranges and immutable target faces/readings.',selection='Compare existing starter one-unit, expanded one-unit and expanded disjoint budget packing. No whole-phrase/fallback/provider change.',density=[.10,.25,.50],knowledge='none, all_function, all_function_and_first25_TRAIN_content_concepts, all_function_and_first50_TRAIN_content_concepts. Global source concept order shared across targets, plural/alias groups excluded together.',packing='Same content-first/TRAIN-rank/longer/source-offset ordering. Take fitting source-disjoint spans, at most one occurrence per concept per message, sum source words <= max(1,floor(n*density)). No whole-sentence replacement.')
 assert not a.output.exists();a.output.write_text(json.dumps(candidate,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summaries));print(sha(a.output))
if __name__=='__main__':main()
