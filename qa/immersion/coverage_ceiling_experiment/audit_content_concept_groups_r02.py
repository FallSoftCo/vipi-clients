#!/usr/bin/env python3
"""Additive diagnostic for four already-documented concept aliases; no frozen score rewrite."""
import copy,hashlib,json
from pathlib import Path
from evaluate_content_expansion_r02 import candidates,select
Q=Path(__file__).resolve().parent;E=Path('/home/ai/Development/investigations/vipi-immersion-reconciliation-20261107-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 audit=json.loads((Q/'source-concept-group-audit-r03.json').read_text());aliases={v:group[0] for group in audit['missing_number_alias_merges'] for v in group};canonical=lambda x:aliases.get(x,x);p=Q/'content-expansion-candidate-r01.json';old=json.loads(p.read_text());new=copy.deepcopy(old)
 for pair in new['pairs'].values():
  for e in pair['entries']:e['concept_id']=canonical(e['concept_id'])
 new['learned_content_global_train_order']=list(dict.fromkeys(canonical(x) for x in old['learned_content_global_train_order']))
 baseline=json.loads((Q/'reviewed-source-unit-native-candidate-r03.json').read_text())
 for lang,pair in baseline['pairs'].items():
  byid={e['id']:e for e in new['pairs'][lang]['entries']}
  for e in pair['entries']:e['concept_id']=byid[e['id']]['concept_id']
 inventory={}
 for lang,pair in old['pairs'].items():
  ids={e['concept_id'] for e in pair['entries'] if e['category']=='content'};inventory[lang]={'declared_content_ids':len(ids),'merged_content_groups':len({canonical(x) for x in ids})}
 effects={}
 for kind in ['diagnostic','fresh']:
  cp=E/f'content-expansion-{kind}-r01.json';capture=json.loads(cp.read_text());changed=[];corrected_selected_concepts={}
  for r in capture['rows']:
   for lang,t in r['targets'].items():
    tokens,bsp,_=candidates(r['text'],baseline,lang);_,esp,_=candidates(r['text'],new,lang)
    for arm,prior in t['arms'].items():
     policy,density,known=arm.split('|');value=select(r['text'],tokens,bsp if policy=='starter_one' else esp,float(density),known,new['learned_content_global_train_order'],policy=='expanded_disjoint');sig=lambda spans:[(s['start'],s['end'],s['translated'],s.get('reading')) for s in spans]
     if sig(value['spans'])!=sig(prior['spans']):changed.append({'id':r['id'],'target':lang,'arm':arm,'prior':sig(prior['spans']),'corrected':sig(value['spans'])})
     corrected_selected_concepts.setdefault((lang,arm),set()).update(s['concept_id'] for s in value['spans'] if s['category']=='content')
  effects[kind]={'capture_sha256':sha(cp),'changed_selected_outputs':changed,'changed_output_count':len(changed),'default25_distinct_content_groups':{lang:len(corrected_selected_concepts[lang,'expanded_disjoint|0.25|none']) for lang in ['sw','ja','es']}}
 out={'production':False,'fresh_validation':False,'scope':'Post-checkpoint correction audit. Frozen candidates, raw captures and scores remain intact. This is a diagnostic replay of concept grouping, not new evidence or a new held-out comparison.','prior_candidate_sha256':sha(p),'existing_group_audit_sha256':sha(Q/'source-concept-group-audit-r03.json'),'alias_groups':audit['missing_number_alias_merges'],'inventory':inventory,'global_declared_content_ids':len(old['learned_content_global_train_order']),'global_merged_content_groups':len(new['learned_content_global_train_order']),'learned_top50_added_after_dedup':sorted(set(new['learned_content_global_train_order'][:50])-set(old['learned_content_global_train_order'][:50])),'effects':effects,'required_future_policy':'Use canonical number/alias groups for both per-message uniqueness and learned-concept exclusion. Do not call declared IDs unique semantic senses.'}
 f=Q/'content-expansion-concept-group-audit-r02.json';assert not f.exists();f.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(sha(f));print(inventory);print({k:{x:v for x,v in e.items() if x!='changed_selected_outputs'} for k,e in effects.items()})
if __name__=='__main__':main()
