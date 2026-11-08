#!/usr/bin/env python3
"""Join frozen independent labels and report source-only lookup research, never native coverage."""
import argparse,collections,hashlib,json,statistics
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def signature(s):return (s['start'],s['end'],s['translated'])
def norm(t):return ' '.join(t.casefold().split())

def main():
 p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();E=a.evidence
 names={'evaluation':'short-conversation-evaluation-r01.json','packet':'short-conversation-all240-review-r01.json','author':'short-conversation-author-review-r01.json','independent':'short-conversation-independent-root-review-r01.json'}
 data={k:json.loads((E/n).read_text()) for k,n in names.items()}; packet={r['id']:r for r in data['packet']['rows']}
 author={s['scope_id']:s for s in data['author']['labels']};independent={s['scope_id']:s for r in data['independent']['rows'] for s in r['scopes']}
 severity={'correct':0,'minor':1,'uncertain':2,'material_error':3,'wrong_scope':3}
 combined={};disagreements=[]
 for sid,x in author.items():
  y=independent.get(sid);labels=[x['meaning']]+([y['combined_judgment']] if y else []);combined[sid]=max(labels,key=lambda v:severity[v])
  if y and x['meaning']!=y['combined_judgment']:disagreements.append({'scope_id':sid,'id':x['id'],'source':x['source'],'target':x['target'],'author':x['meaning'],'independent':y['combined_judgment'],'independent_reason':y['reason'],'aggregation':'more cautious label retained; original labels unchanged'})
 def label(r,lang,s):
  q=packet[r['id']+'-en-'+lang];found=[z for z in q['scopes'] if signature(z)==signature(s)];assert len(found)==1,(r['id'],lang,s);return combined[found[0]['scope_id']]
 def metric(rows,lang,arm):
  n=len(rows);totalwords=sum(r['targets'][lang]['source_words'] for r in rows);strict=clean=content=raw=bad=0;sd=[];ld=[];cd=[];changed=contentwords=0;distinct=set();cnt=collections.Counter()
  for r in rows:
   t=r['targets'][lang];sp=t['arms'][arm]['spans'];labs=[label(r,lang,s) for s in sp];good=[s for s,l in zip(sp,labs) if l in ('correct','minor')];exact=[s for s,l in zip(sp,labs) if l=='correct'];nw=t['source_words'];cw=sum(s['changed_source_words'] for s in good);co=sum(s['content_source_words'] for s in good)
   raw+=bool(sp);strict+=bool(sp) and all(l=='correct' for l in labs);clean+=bool(sp) and all(l in ('correct','minor') for l in labs);content+=bool(co) and all(l in ('correct','minor') for l in labs);bad+=any(l not in ('correct','minor') for l in labs)
   sd.append(sum(s['changed_source_words'] for s in exact)/nw if nw else 0);ld.append(cw/nw if nw else 0);cd.append(co/nw if nw else 0);changed+=cw;contentwords+=co
   distinct.update(s['lexicon_id'] for s in good);cnt.update(labs)
  return {'messages':n,'raw_changed_messages':raw,'strict_clean_messages':strict,'minor_tolerant_clean_messages':clean,'clean_content_messages':content,'material_or_uncertain_messages':bad,'strict_mean_changed_depth':statistics.mean(sd) if n else 0,'minor_tolerant_mean_changed_depth':statistics.mean(ld) if n else 0,'mean_content_anchor_depth':statistics.mean(cd) if n else 0,'word_weighted_changed_depth':changed/totalwords if totalwords else 0,'word_weighted_content_anchor_depth':contentwords/totalwords if totalwords else 0,'distinct_selected_unit_ids':len(distinct),'scope_labels':dict(cnt)}
 rows=data['evaluation']['rows'];arms=list(rows[0]['targets']['sw']['arms']);unique=list({norm(r['text']):r for r in reversed(rows)}.values())
 views={'message_weighted':rows,'unique_normalized_text':unique,'novel_vs_train_surface':[r for r in rows if not r['train_surface_overlap']],'novel_vs_prior_seen_surface':[r for r in rows if not r['previously_evaluated_or_seen_surface_overlap']],'novel_vs_both_surfaces':[r for r in rows if not r['train_surface_overlap'] and not r['previously_evaluated_or_seen_surface_overlap']]}
 for b in ['1-5','6-15','16-30']:views['length_'+b]=[r for r in rows if r['sampling_length_bin']==b]
 results={lang:{view:{arm:metric(rr,lang,arm) for arm in arms} for view,rr in views.items()} for lang in ['sw','ja','es']}
 refs={};marginal={}
 for lang in results:
  whole=[];embedded=[];auto=[];reject_budget=[];unit_ids=set();formula=[]
  for r in rows:
   t=r['targets'][lang]
   if t['whole_reference_units']:whole.append(r['id'])
   if t['embedded_reference_units']:embedded.append(r['id'])
   for s in t['whole_reference_units']+t['embedded_reference_units']:
    assert label(r,lang,s) in ('correct','minor');unit_ids.add(s['lexicon_id']);formula.append({'id':r['id'],'source':s['original'],'target':s['translated'],'words':s['changed_source_words'],'budget':t['arms']['starter_plus_units_none']['native_budget_proxy'],'whole':s['whole_message'],'selected_automatic':any(signature(z)==signature(s) for z in t['arms']['starter_plus_units_none']['spans'])})
   if any(s['source_kind']=='complete_short_unit' for s in t['arms']['starter_plus_units_none']['spans']):auto.append(r['id'])
   if any(s.get('source_kind')=='complete_short_unit' and s.get('reason')=='native_budget_proxy_exceeded' for s in t['arms']['starter_plus_units_none']['rejected']):reject_budget.append(r['id'])
  refs[lang]={'whole_message_reference_messages':len(whole),'embedded_reference_messages':len(embedded),'union_reference_messages':len(set(whole+embedded)),'distinct_matched_short_unit_ids':len(unit_ids),'automatic_selected_short_unit_messages':len(auto),'messages_with_short_unit_budget_rejection':len(reject_budget),'exact_units':formula}
  marginal[lang]={}
  for known in ['none','i_and_but','all_function']:
   b='starter_'+known;c='starter_plus_units_'+known;before=results[lang]['message_weighted'][b];after=results[lang]['message_weighted'][c]
   marginal[lang][known]={'clean_message_gain':after['minor_tolerant_clean_messages']-before['minor_tolerant_clean_messages'],'clean_content_message_gain':after['clean_content_messages']-before['clean_content_messages'],'mean_correct_depth_gain':after['minor_tolerant_mean_changed_depth']-before['minor_tolerant_mean_changed_depth'],'mean_content_depth_gain':after['mean_content_anchor_depth']-before['mean_content_anchor_depth']}
 out={'schema':'vipi-short-conversation-joined-decision-r01','production':False,'inputs':{k:{'file':n,'sha256':sha(E/n)} for k,n in names.items()},'review_join':{'author_scopes':len(author),'independent_scopes':len(independent),'exact_label_agreements':sum(author[k]['meaning']==v['combined_judgment'] for k,v in independent.items()),'disagreements':disagreements,'combined_counts':dict(collections.Counter(combined.values()))},'sampling':{'messages':len(rows),'unique_normalized_texts':len(unique),'distinct_conversations':len(set(r['conversation_index'] for r in rows)),'train_surface_overlap':sum(r['train_surface_overlap'] for r in rows),'prior_seen_surface_overlap':sum(r['previously_evaluated_or_seen_surface_overlap'] for r in rows),'overlap_union':sum(r['train_surface_overlap'] or r['previously_evaluated_or_seen_surface_overlap'] for r in rows),'length_bins':dict(collections.Counter(r['sampling_length_bin'] for r in rows))},'results':results,'complete_reference_availability':refs,'marginal_gain_over_reviewed_starter_projection':marginal,'interpretation':['No additional clean messages or content depth is credited merely for an available on-demand reference.','Current native production/full-MT runtime is not this source-word control. Zero translation providers called by this Python experiment.','Known-face views are simulations, not a shipped progression feature.','The 10% native-budget proxy is quantized and can exceed 10% on short inputs; complete units larger than budget are rejected, never silently forced.','BST is a length-stratified English role-play sample with reviewed contexts, not representative worldwide chat frequency or a 110-direction release claim.','Assistant labels, independently frozen for the selected subset, are not certified human bilingual ground truth.']}
 a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print('SHA',sha(a.out));print('sampling',out['sampling']);print('join',out['review_join'])
 for lang in results:
  print(lang)
  for arm in arms:
   m=results[lang]['message_weighted'][arm];print(arm,'clean',m['minor_tolerant_clean_messages'],'strict',m['strict_clean_messages'],'content',m['clean_content_messages'],'depth',round(m['minor_tolerant_mean_changed_depth']*100,3),'contentdepth',round(m['mean_content_anchor_depth']*100,3))
  print('refs',{k:v for k,v in refs[lang].items() if k!='exact_units'});print('marginal',marginal[lang])
if __name__=='__main__':main()
