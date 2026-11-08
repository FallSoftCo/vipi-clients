#!/usr/bin/env python3
"""Secondary density diagnostic: same already-reviewed contexts, matcher and one-unit cap."""
import argparse, collections, hashlib, json, math, statistics
from pathlib import Path
import evaluate_short_conversation_units as primary
from evaluate_short_conversation_units import key

def select(text,tokens,eligible,known='none',density=0.10):
    filtered=[];rejected=[];budget=max(1,math.floor(len(tokens)*density))
    for s in eligible:
        reason=None
        if known=='i_and_but' and key(s['original'].strip('.!?')) in {'i','and','but'}:reason='simulated_known_face'
        elif known=='all_function' and s['category']=='function':reason='simulated_known_function_unit'
        elif s['changed_source_words']>budget:reason='native_budget_proxy_exceeded'
        if reason:rejected.append(dict(s,reason=reason))
        else:filtered.append(s)
    filtered.sort(key=lambda s:(s['category']!='content',s['train_rank'],-s['changed_source_words'],s['start'],s['lexicon_id']))
    chosen=filtered[:1]
    output=text
    if chosen:
        s=chosen[0];output=text[:s['start']]+s['translated']+text[s['end']:]
    n=len(tokens)
    return dict(spans=chosen,mixed_text=output,native_budget_proxy=budget,
        changed_depth=sum(s['changed_source_words'] for s in chosen)/n if n else 0,
        content_anchor_depth=sum(s['content_source_words'] for s in chosen)/n if n else 0,
        rejected=rejected)


def signature(s):return (s['start'],s['end'],s['translated'])
def main():
 p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();Q=Path(__file__).resolve().parent;E=a.evidence
 freeze=json.loads((Q/'short-conversation-evaluation-freeze-r01.json').read_text())
 for n,h in freeze['files'].items():assert primary.sha(Q/n)==h
 protocol=json.loads((Q/'short-conversation-context-heldout-r01.json').read_text());pack=json.loads((Q/'reviewed-source-unit-native-candidate-r03.json').read_text());targets={l:json.loads((Q/f'short-conversation-targets-en-{l}-r02.json').read_text()) for l in ['sw','ja','es']}
 old=json.loads((E/'short-conversation-evaluation-r01.json').read_text());packet=json.loads((E/'short-conversation-all240-review-r01.json').read_text());author=json.loads((E/'short-conversation-author-review-r01.json').read_text());root=json.loads((E/'short-conversation-independent-root-review-r01.json').read_text())
 labels={x['scope_id']:x['meaning'] for x in author['labels']};severity={'correct':0,'minor':1,'uncertain':2,'material_error':3,'wrong_scope':3}
 for r in root['rows']:
  for x in r['scopes']:labels[x['scope_id']]=max([labels[x['scope_id']],x['combined_judgment']],key=lambda v:severity[v])
 lookup={(r['source_case_id'],r['target_language'],signature(s)):labels[s['scope_id']] for r in packet['rows'] for s in r['scopes']}
 cached={}
 for c in protocol['cases']:
  for l,t in targets.items():
   tokens,words,reject=primary.starter_candidates(c['text'],pack,l);units,ureject=primary.complete_units(c['text'],t);cached[c['id'],l]=(tokens,words,units)
 # Exact structural parity at frozen10%; only the budget multiplier is parameterized.
 for r in old['rows']:
  for l in targets:
   tokens,words,units=cached[r['id'],l]
   for arm in ['starter','starter_plus_units']:
    for known in ['none','i_and_but','all_function']:
     assert select(r['text'],tokens,words+(units if arm=='starter_plus_units' else []),known,.10)==r['targets'][l]['arms'][arm+'_'+known]
 rows=[];unreviewed=[]
 for density in [.25,.50]:
  for c in protocol['cases']:
   for l in targets:
    tokens,words,units=cached[c['id'],l]
    arms={}
    for arm in ['starter','starter_plus_units']:
     for known in ['none','i_and_but','all_function']:
      v=select(c['text'],tokens,words+(units if arm=='starter_plus_units' else []),known,density)
      for s in v['spans']:
       k=(c['id'],l,signature(s));s=dict(s)
       if k not in lookup:unreviewed.append({'id':c['id'],'target':l,'density':density,'span':s})
      v['labels']=[lookup.get((c['id'],l,signature(s)),'unreviewed') for s in v['spans']];arms[arm+'_'+known]=v
    rows.append({'id':c['id'],'text':c['text'],'target':l,'density':density,'source_words':len(tokens),'sampling_length_bin':c['sampling_length_bin'],'arms':arms})
 metrics={}
 for density in [.25,.50]:
  metrics[str(density)]={}
  for lang in targets:
   views={'all':[r for r in rows if r['density']==density and r['target']==lang]}
   views.update({b:[r for r in views['all'] if r['sampling_length_bin']==b] for b in ['1-5','6-15','16-30']})
   res={}
   for view,rr in views.items():
    res[view]={}
    for arm in rr[0]['arms']:
     n=len(rr);m={'messages':n,'strict_clean':0,'minor_tolerant_clean':0,'clean_content':0,'unreviewed_or_bad':0,'selected_complete_units':0};depth=[];content=[]
     for r in rr:
      v=r['arms'][arm];sp=v['spans'];ll=v['labels'];clean=bool(sp) and all(x in ['correct','minor'] for x in ll);m['strict_clean']+=bool(sp) and all(x=='correct' for x in ll);m['minor_tolerant_clean']+=clean;m['clean_content']+=clean and any(s['content_source_words'] for s in sp);m['unreviewed_or_bad']+=any(x not in ['correct','minor'] for x in ll);m['selected_complete_units']+=any(s['source_kind']=='complete_short_unit' for s in sp);depth.append(v['changed_depth'] if clean else 0);content.append(v['content_anchor_depth'] if clean else 0)
     m['mean_correct_depth']=statistics.mean(depth);m['mean_content_depth']=statistics.mean(content);res[view][arm]=m
   metrics[str(density)][lang]=res
 out={'production':False,'fresh_evaluation':False,'requested_densities':[.25,.50],'actual_app_default':.25,'app_default_source_locations':['ios/Vipi/AppState.swift:56','android/app/src/main/java/co/fallsoft/vipi/VipiModel.kt:43'],'purpose':'Post-primary structural density diagnosis on already-reviewed same80, not a policy selection or new holdout.','changed_from_primary':'Only source-word budget multiplier. Same complete-boundary matcher, target data, content/rank selector, known-face filters, and at-most-one selected unit.','ten_percent_parity_all240_six_arms':True,'primary_freeze_sha256':primary.sha(Q/'short-conversation-evaluation-freeze-r01.json'),'primary_evaluation_sha256':primary.sha(E/'short-conversation-evaluation-r01.json'),'unreviewed_new_scopes':unreviewed,'metrics':metrics,'rows':rows,'limits':['Current native runtime is not projected here.','One-unit cap remains; this does not test filling25/50percent with multiple words.','Reused references/contexts/labels; not fresh semantic validation.','No production or native pack promotion.']}
 assert not a.output.exists();a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(primary.sha(a.output));print('unreviewed',len(unreviewed))
 for d,langs in metrics.items():
  for l,v in langs.items():
   print(d,l)
   for arm,m in v['all'].items(): print(arm,'clean',m['minor_tolerant_clean'],'content',m['clean_content'],'depth',round(m['mean_correct_depth']*100,3),'contentdepth',round(m['mean_content_depth']*100,3),'units',m['selected_complete_units'])
if __name__=='__main__':main()
