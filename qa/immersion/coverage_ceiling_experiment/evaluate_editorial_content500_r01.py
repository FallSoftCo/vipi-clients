#!/usr/bin/env python3
"""Frozen TRAIN comparison of broader editorial content and shared role guards."""
import argparse,collections,hashlib,json,math,time
from pathlib import Path
from evaluate_content_expansion_r01 import candidates as old_candidates
from evaluate_reviewed_words import WORD,u16
from editorial_common_roles_r01 import context,eligible
from evaluate_role_content_r02 import choose
Q=Path(__file__).resolve().parent
DENSITIES=(.10,.25,.50)
KNOWLEDGE=('none','all_function','all_function_global50','all_function_global100','all_function_global300')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def emit(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def run(text,baseline,candidate,language):
 tokens,old,_=old_candidates(text,baseline,language);assert [(x.start(),x.end()) for x in tokens]==[(x.start(),x.end()) for x in WORD.finditer(text)]
 entries=[e for e in candidate['entries'] if e['language']==language];source_roles=collections.defaultdict(set)
 for e in candidate['entries']:source_roles[e['source']].add(e['pos'])
 for s in old:
  if s['category']=='content':source_roles[s['original'].casefold().replace('’',"'")].add(s.get('pos','noun'))
 ctxs={i:context(text,tokens,i,candidate['capitalized_homographs']) for i in range(len(tokens))};index={(t.start(),t.end()):i for i,t in enumerate(tokens)}
 common_old=[];rejected=[]
 for s in old:
  w=s['original'].casefold().replace('’',"'")
  if s['category']=='content':
   s['concept_id']=candidate['source_families'].get(w) or s['concept_id']
   i=index.get((s['start'],s['end']))
   if i is None:allowed,reason=False,'content_unit_role_not_qualified'
   else:allowed,reason=eligible(ctxs[i],s.get('pos','noun'),source_roles)
   if not allowed:rejected.append({'source_kind':'reviewed_starter','original':s['original'],'start':s['start'],'end':s['end'],'reason':reason});continue
  common_old.append(s)
 added=[];by_source=collections.defaultdict(list)
 for e in entries:by_source[e['source']].append(e)
 for i,t in enumerate(tokens):
  w=t.group().casefold().replace('’',"'")
  for e in by_source.get(w,[]):
   allowed,reason=eligible(ctxs[i],e['pos'],source_roles,e['source_form_kind'])
   if not allowed:rejected.append({'source_kind':'editorial_primary','original':t.group(),'start':t.start(),'end':t.end(),'reason':reason,'entry_id':e['id']});continue
   added.append({'start':t.start(),'end':t.end(),'sourceStartUTF16':u16(text[:t.start()]),'sourceEndUTF16':u16(text[:t.end()]),'original':t.group(),'translated':e['target'],'reading':e['reading'],'reading_kana':e['reading_kana'],'category':'content','pos':e['pos'],'concept_id':e['concept_id'],'lexicon_id':e['id'],'train_rank':e['train_rank'],'changed_source_words':1,'content_source_words':1,'source_kind':'editorial_primary','guard':'shared_'+e['pos'],'contextual_alternative_risk':e['contextual_alternative_risk']})
 # Prefer an existing reviewed face for the same source occurrence/concept. This
 # expansion does not silently replace prior target choices with new guesses.
 existing={(s['start'],s['end'],s['concept_id']) for s in common_old}
 added=[s for s in added if (s['start'],s['end'],s['concept_id']) not in existing]
 result={}
 for density in DENSITIES:
  for known in KNOWLEDGE:
   for arm,spans in [('reviewed_control',old),('common_guard_control',common_old),('editorial500',common_old+added)]:
    result[f'{arm}|{density:.2f}|{known}']=choose(text,tokens,spans,density,known,candidate['learned_family_order'])
 return {'source_words':len(tokens),'arms':result,'rejections':rejected,'added_candidates':added}
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--train',type=Path,required=True);p.add_argument('--contrasts',type=Path,required=True);p.add_argument('--freeze',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--prepare-freeze',action='store_true');a=p.parse_args();inputs={'candidate':a.candidate,'train':a.train,'baseline':Q/'content-expansion-candidate-r01.json','contrasts':a.contrasts,'runner':Path(__file__),'common_roles':Q/'editorial_common_roles_r01.py','selection':Q/'evaluate_role_content_r02.py','baseline_candidates':Q/'evaluate_content_expansion_r01.py'}
 if a.prepare_freeze:
  assert not a.freeze.exists();emit(a.freeze,{'production':False,'frozen_before_context_outputs':True,'inputs':{k:{'path':str(v),'sha256':sha(v)} for k,v in inputs.items()},'corpus':'All9535 free-human ConvAI2 role-play TRAIN messages, diagnostic; no new holdout.','arms':['unchanged reviewed-content RESEARCH control (not app runtime)','shared role guard on that control','shared role guard + editorial500 primary targets with existing reviewed face precedence'],'densities':DENSITIES,'knowledge':KNOWLEDGE,'quality':'Raw reach/depth never implies correct meaning. Fixed contextual review before semantic aggregates. Human/assistant judgment distinguished.','review_selection':'Per language32 default25 new-selected contexts: first12 by salted source-ID hash among known300 survivors, next12 among none-known new contexts, next8 among high-risk primary-context alternatives; unique source IDs where possible. One added span chosen by salted scope hash per context. Preserve prior context for review only.','safety':'Same source eligibility gate across old/new paths; authored safety-negative contrasts kept separate from corpus. No complete machine-translation fallback or new provider call.'});print('freeze',sha(a.freeze));return
 f=json.loads(a.freeze.read_text())
 for k,p in inputs.items():assert sha(p)==f['inputs'][k]['sha256'],k
 assert sha(a.train)=='a5a9672c3e2e8a2f3d740cb0b61810ad46f3e3cd7bbe86b8d79962c6b34ad33c';candidate=json.loads(a.candidate.read_text());baseline=json.loads(inputs['baseline'].read_text());train=json.loads(a.train.read_text());cases=[{'id':f'bst-train-{ci:04d}-{ti:02d}','text':text,'preceding_context_for_review':c['dialog'][:ti]} for ci,c in enumerate(train) if c['context_dataset']=='convai2' for ti,(speaker,text) in enumerate(c['dialog']) if speaker==0 and text.strip()];assert len(cases)==9535
 started=time.monotonic();metrics={};pools=collections.defaultdict(list);rejections=collections.Counter()
 for case in cases:
  for language in ['sw','ja','es']:
   out=run(case['text'],baseline,candidate,language);n=out['source_words'];rejections.update((language,x['source_kind'],x['reason']) for x in out['rejections'])
   for key,s in out['arms'].items():
    for view in ['all','length_'+('1-5' if n<=5 else '6-15' if n<=15 else '16+')]:
     m=metrics.setdefault((language,view,key),{'messages':0,'available':0,'content_available':0,'changed':0,'content_changed':0,'words':0,'depth_sum':0.,'content_depth_sum':0.,'concepts':set(),'new_concepts':set(),'new_selected_messages':0,'whole_message_changed':0})
     m['messages']+=1;m['available']+=bool(s['spans']);m['content_available']+=bool(s['content_source_words']);m['changed']+=s['changed_source_words'];m['content_changed']+=s['content_source_words'];m['words']+=n;m['depth_sum']+=s['changed_source_words']/n if n else 0;m['content_depth_sum']+=s['content_source_words']/n if n else 0;m['concepts'].update(x['concept_id'] for x in s['spans'] if x['category']=='content');m['new_concepts'].update(x['concept_id'] for x in s['spans'] if x['source_kind']=='editorial_primary');m['new_selected_messages']+=any(x['source_kind']=='editorial_primary' for x in s['spans']);m['whole_message_changed']+=bool(n and s['changed_source_words']==n)
   default=out['arms']['editorial500|0.25|none'];known=out['arms']['editorial500|0.25|all_function_global300'];new=[x for x in default['spans'] if x['source_kind']=='editorial_primary'];new300=[x for x in known['spans'] if x['source_kind']=='editorial_primary']
   if new or new300:pools[language].append({**case,'language':language,'source_words':n,'default25':default,'known300_25':known,'reviewed_control25':out['arms']['reviewed_control|0.25|none'],'common_guard_control25':out['arms']['common_guard_control|0.25|none'],'new':new,'new300':new300,'rejections':out['rejections']})
 summary=[]
 for (language,view,key),m in metrics.items():
  row={k:v for k,v in m.items() if not isinstance(v,set) and not k.endswith('_sum')};row.update(language=language,view=view,arm=key,message_mean_depth=m['depth_sum']/m['messages'],message_mean_content_depth=m['content_depth_sum']/m['messages'],word_weighted_content_depth=m['content_changed']/m['words'] if m['words'] else 0,distinct_content_concepts=len(m['concepts']),distinct_new_concepts=len(m['new_concepts']),content_concepts=sorted(m['concepts']),new_concepts=sorted(m['new_concepts']));summary.append(row)
 contrast_results=[]
 for case in json.loads(a.contrasts.read_text())['cases']:
  for language in ['sw','ja','es']:
   r=run(case['text'],baseline,candidate,language);selection=r['arms']['editorial500|0.50|none'];forbidden=[s for s in selection['spans'] if s['original'].casefold() in case.get('forbidden_sources',[])];tokens=list(WORD.finditer(case['text']));roles=collections.defaultdict(set)
   for e in candidate['entries']:roles[e['source']].add(e['pos'])
   probes=[eligible(context(case['text'],tokens,i,candidate['capitalized_homographs']),case['role_probe_pos'],roles) for i,t in enumerate(tokens) if t.group().casefold()==case['role_probe_source']]
   actual=any(x[0] for x in probes)
   contrast_results.append({'id':case['id'],'language':language,'text':case['text'],'selected':selection,'forbidden_selected':forbidden,'rejections':r['rejections'],'direct_shared_role_probes':probes,'role_expectation_passed':actual==case['expected_shared_role']})
 packet=[]
 for language,rows in pools.items():
  selected=set()
  for stratum,count,predicate,scope_key in [('known300',12,lambda r:bool(r['new300']),'new300'),('default',12,lambda r:bool(r['new']),'new'),('common_alternative',8,lambda r:any(s['contextual_alternative_risk'] for s in r['new']),'new')]:
   eligible_rows=[r for r in rows if r['id'] not in selected and predicate(r)];eligible_rows.sort(key=lambda r:hashlib.sha256(('vipi-editorial500-r01|'+language+'|'+stratum+'|'+r['id']).encode()).hexdigest())
   for r in eligible_rows[:count]:
    selected.add(r['id']);scopes=r[scope_key];scopes=sorted(scopes,key=lambda s:hashlib.sha256((r['id']+'|'+s['lexicon_id']+'|'+str(s['start'])).encode()).hexdigest());span=scopes[0];e=next(e for e in candidate['entries'] if e['id']==span['lexicon_id']);packet.append({**r,'review_stratum':stratum,'selected_review_scope':span,'primary_entry':e})
 out={'production':False,'semantic_approval':False,'freeze_sha256':sha(a.freeze),'source_messages':len(cases),'provider_calls':0,'summary':summary,'rejections':[{'language':k[0],'source_kind':k[1],'reason':k[2],'count':v} for k,v in sorted(rejections.items())],'contrast_results':contrast_results,'review_packet':packet,'all_new_selected_contexts':dict(pools),'elapsed_seconds':time.monotonic()-started,'limits':['TRAIN role-play raw selection, not unseen semantic quality or native timing.','Only source-only lexical faces; no full-machine-translation credit.','Broader output still depends on ordinary-sense editorial choices and shared local role approximation.']};assert not a.output.exists();emit(a.output,out);print('output',sha(a.output),'review_rows',len(packet),'seconds',out['elapsed_seconds'])
if __name__=='__main__':main()
