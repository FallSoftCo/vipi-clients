#!/usr/bin/env python3
"""Frozen source-only content/packing comparison; never changes native policy."""
import argparse,collections,hashlib,json,math,time
from pathlib import Path
from evaluate_short_conversation_units import starter_candidates,sha
Q=Path(__file__).resolve().parent
DENSITIES=(.10,.25,.50)
KNOWN=('none','all_function','all_function_top25_content','all_function_top50_content')
ARMS=('starter_one','expanded_one','expanded_disjoint')

def candidates(text,pack,lang):
 tokens,spans,reject=starter_candidates(text,pack,lang);byid={e['id']:e for e in pack['pairs']['en-'+lang]['entries']}
 for s in spans:s['concept_id']=byid[s['lexicon_id']]['concept_id']
 return tokens,spans,reject

def select(text,tokens,spans,density,known,learned,multiple):
 budget=max(1,math.floor(len(tokens)*density));limit=25 if known.endswith('top25_content') else 50 if known.endswith('top50_content') else 0;known_concepts=set(learned[:limit]);eligible=[];rejected=collections.Counter()
 for s in spans:
  if known!='none' and s['category']=='function':rejected['function_known']+=1
  elif s['category']=='content' and s['concept_id'] in known_concepts:rejected['content_concept_known']+=1
  elif s['changed_source_words']>budget:rejected['unit_exceeds_budget']+=1
  else:eligible.append(s)
 eligible.sort(key=lambda s:(s['category']!='content',s['train_rank'],-s['changed_source_words'],s['start'],s['lexicon_id']))
 chosen=[];used=0;seen=set()
 for s in eligible:
  if s['concept_id'] in seen:rejected['same_concept_already_selected']+=1;continue
  if any(s['start']<t['end'] and t['start']<s['end'] for t in chosen):rejected['source_overlap']+=1;continue
  if used+s['changed_source_words']>budget:rejected['remaining_budget']+=1;continue
  chosen.append(s);used+=s['changed_source_words'];seen.add(s['concept_id'])
  if not multiple:break
 chosen.sort(key=lambda s:s['start']);out=text
 for s in reversed(chosen):out=out[:s['start']]+s['translated']+out[s['end']:]
 assert used<=budget
 for s in chosen:assert text[s['start']:s['end']]==s['original']
 return {'spans':chosen,'mixed_text':out,'budget':budget,'changed_source_words':used,'content_source_words':sum(s['content_source_words'] for s in chosen),'rejected_counts':dict(rejected)}

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--kind',choices=['train','diagnostic','fresh'],required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();freeze=json.loads((Q/'content-expansion-evaluation-freeze-r02.json').read_text())
 for n,h in freeze['files'].items():assert sha(Q/n)==h,(n,'freeze mismatch')
 expanded=json.loads((Q/'content-expansion-candidate-r01.json').read_text());baseline=json.loads((Q/'reviewed-source-unit-native-candidate-r03.json').read_text())
 for lang,pair in baseline['pairs'].items():
  byid={e['id']:e for e in expanded['pairs'][lang]['entries']}
  for e in pair['entries']:e['concept_id']=byid[e['id']]['concept_id']
 if a.kind=='train':
  assert sha(a.input)==freeze['training_sha256'];raw=json.loads(a.input.read_text());cases=[{'id':f'bst-train-{ci:04d}-{ti:02d}','text':text,'sampling_length_bin':'1-5' if len(text.split())<=5 else '6-15' if len(text.split())<=15 else '16+'} for ci,c in enumerate(raw) if c['context_dataset']=='convai2' for ti,(speaker,text) in enumerate(c['dialog']) if speaker==0 and text.strip()]
 else:
  protocol=json.loads(a.input.read_text());cases=protocol['cases']
  if a.kind=='diagnostic':assert sha(a.input)==freeze['diagnostic_protocol_sha256']
  else:assert protocol['policy_freeze_sha256']==sha(Q/'content-expansion-evaluation-freeze-r02.json')
 learned=expanded['learned_content_global_train_order'];metrics={};rows=[];started=time.perf_counter()
 for c in cases:
  text=c['text'];targets={}
  for lang in ['sw','ja','es']:
   tokens,bsp,brej=candidates(text,baseline,lang);ntokens,esp,erej=candidates(text,expanded,lang);assert [(m.start(),m.end(),m.group()) for m in tokens]==[(m.start(),m.end(),m.group()) for m in ntokens];arms={}
   for d in DENSITIES:
    for known in KNOWN:
     for arm in ARMS:
      result=select(text,tokens,bsp if arm=='starter_one' else esp,d,known,learned,arm=='expanded_disjoint');key=f'{arm}|{d:.2f}|{known}';arms[key]=result
      for view in ['all','length_'+c.get('sampling_length_bin','unknown')]:
       mk=(lang,view,key);m=metrics.setdefault(mk,{'messages':0,'raw_available':0,'raw_content_available':0,'source_words':0,'changed_source_words':0,'content_source_words':0,'depth_sum':0.,'content_depth_sum':0.,'concepts':set(),'content_concepts':set(),'selected_scopes':0});m['messages']+=1;m['raw_available']+=bool(result['spans']);m['raw_content_available']+=bool(result['content_source_words']);m['source_words']+=len(tokens);m['changed_source_words']+=result['changed_source_words'];m['content_source_words']+=result['content_source_words'];m['depth_sum']+=result['changed_source_words']/len(tokens) if tokens else 0;m['content_depth_sum']+=result['content_source_words']/len(tokens) if tokens else 0;m['concepts'].update(s['concept_id'] for s in result['spans']);m['content_concepts'].update(s['concept_id'] for s in result['spans'] if s['category']=='content');m['selected_scopes']+=len(result['spans'])
   if a.kind!='train':targets[lang]={'source_words':len(tokens),'arms':arms,'source_rejection_counts':{'baseline':dict(collections.Counter(x['reason'] for x in brej)),'expanded':dict(collections.Counter(x['reason'] for x in erej))}}
  if a.kind!='train':rows.append(dict(c,targets=targets))
 summary={}
 for (lang,view,key),m in metrics.items():
  m['mean_raw_depth']=m.pop('depth_sum')/m['messages'];m['mean_raw_content_depth']=m.pop('content_depth_sum')/m['messages'];m['distinct_concepts']=len(m['concepts']);m['distinct_content_concepts']=len(m['content_concepts']);m['concepts']=sorted(m['concepts']);m['content_concepts']=sorted(m['content_concepts']);summary.setdefault(lang,{}).setdefault(view,{})[key]=m
 out={'production':False,'kind':a.kind,'semantic_review':'pending; raw eligible reach is not correct reach','provider_calls':0,'current_native_control':False,'boundary_source':'Frozen Python English source boundary/protection functions, no new native qualification.','input_sha256':sha(a.input),'policy_freeze_sha256':sha(Q/'content-expansion-evaluation-freeze-r02.json'),'elapsed_seconds':time.perf_counter()-started,'source_messages':len(cases),'summary':summary,'rows':rows}
 assert not a.output.exists();a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(sha(a.output));print('source messages',len(cases),'elapsed',round(out['elapsed_seconds'],3))
 for lang in summary:
  for arm in ARMS:
   m=summary[lang]['all'][arm+'|0.25|none'];print(lang,arm,m['raw_available'],m['raw_content_available'],round(100*m['mean_raw_depth'],2),round(100*m['mean_raw_content_depth'],2),m['distinct_content_concepts'])
if __name__=='__main__':main()
