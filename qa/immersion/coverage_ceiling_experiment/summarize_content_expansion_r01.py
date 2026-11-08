#!/usr/bin/env python3
"""Score exact reviewed source ranges; raw lookup rate never substitutes for meaning."""
import argparse,collections,hashlib,json
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for x in ['capture','packet','labels','output']:p.add_argument('--'+x,type=Path,required=True)
 a=p.parse_args();capture=json.loads(a.capture.read_text());packet=json.loads(a.packet.read_text());labels=json.loads(a.labels.read_text());byid={x['scope_id']:x['meaning'] for x in labels['labels']};bykey={(r['source_case_id'],r['target_language'],s['start'],s['end'],s['translated']):byid[s['scope_id']] for r in packet['rows'] for s in r['scopes']};metrics={}
 for r in capture['rows']:
  for lang,t in r['targets'].items():
   for arm,v in t['arms'].items():
    sp=v['spans'];ll=[bykey[r['id'],lang,s['start'],s['end'],s['translated']] for s in sp];correct=[s for s,l in zip(sp,ll) if l in ['correct','minor']];strict=[s for s,l in zip(sp,ll) if l=='correct'];clean=bool(sp) and len(correct)==len(sp)
    for view in ['all','length_'+r.get('sampling_length_bin','unknown')]:
     key=(lang,view,arm);m=metrics.setdefault(key,dict(messages=0,strict_clean_messages=0,minor_tolerant_clean_messages=0,clean_content_messages=0,material_or_uncertain_messages=0,strict_depth_sum=0.,correct_depth_sum=0.,content_depth_sum=0.,distinct_content_concepts=set(),distinct_concepts=set(),scope_labels=collections.Counter()));m['messages']+=1;m['strict_clean_messages']+=bool(sp) and len(strict)==len(sp);m['minor_tolerant_clean_messages']+=clean;m['clean_content_messages']+=clean and any(s['content_source_words'] for s in correct);m['material_or_uncertain_messages']+=bool(sp) and not clean;den=t['source_words'];m['strict_depth_sum']+=sum(s['changed_source_words'] for s in strict)/den if den else 0;m['correct_depth_sum']+=sum(s['changed_source_words'] for s in correct)/den if den else 0;m['content_depth_sum']+=sum(s['content_source_words'] for s in correct)/den if den else 0;m['distinct_concepts'].update(s['concept_id'] for s in correct);m['distinct_content_concepts'].update(s['concept_id'] for s in correct if s['category']=='content');m['scope_labels'].update(ll)
 result={}
 for (lang,view,arm),m in metrics.items():
  for name in ['strict','correct','content']:m['mean_'+name+'_depth']=m.pop(name+'_depth_sum')/m['messages']
  m['distinct_concept_count']=len(m['distinct_concepts']);m['distinct_content_concept_count']=len(m['distinct_content_concepts']);m['distinct_concepts']=sorted(m['distinct_concepts']);m['distinct_content_concepts']=sorted(m['distinct_content_concepts']);result.setdefault(lang,{}).setdefault(view,{})[arm]=m
 out={'production':False,'kind':capture['kind'],'input_hashes':{x:sha(getattr(a,x)) for x in ['capture','packet','labels']},'policy_freeze_sha256':capture['policy_freeze_sha256'],'current_native_runtime':False,'provider_calls':0,'metrics':result,'limits':['Semantic labels apply only to exact inspected scopes; primary evidence alone is not meaning approval.','All simulated learned-concept states are research, not a shipped learning model.','At most one instance per concept in disjoint packing; source word budget is preserved.']};assert not a.output.exists();a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(sha(a.output))
 for lang,views in result.items():
  print(lang)
  for k in ['starter_one|0.25|none','expanded_one|0.25|none','expanded_disjoint|0.25|none','expanded_disjoint|0.25|all_function','expanded_disjoint|0.25|all_function_top25_content','expanded_disjoint|0.25|all_function_top50_content']:
   m=views['all'][k];print(k,m['minor_tolerant_clean_messages'],m['strict_clean_messages'],m['clean_content_messages'],round(100*m['mean_correct_depth'],2),round(100*m['mean_content_depth'],2),m['distinct_content_concept_count'])
if __name__=='__main__':main()
