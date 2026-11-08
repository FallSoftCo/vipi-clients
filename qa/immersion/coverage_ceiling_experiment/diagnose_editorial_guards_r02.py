#!/usr/bin/env python3
"""TRAIN-only ablation of shared source-role guards. No candidate face changes."""
import argparse,collections,hashlib,json,re,time
from pathlib import Path
import evaluate_editorial_content500_r01 as base
import editorial_common_roles_r01 as guard
from evaluate_reviewed_words import WORD,PROTECTED
Q=Path(__file__).resolve().parent
ARMS=('control','scoped_literals','noun_only','combined')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def quoted_ranges(text):
 out=[];i=0
 while i<len(text):
  marker=next((m for m in ('```','`','“','"') if text.startswith(m,i)),None)
  if not marker or (i and text[i-1]=='\\'):i+=1;continue
  closing='”' if marker=='“' else marker;j=text.find(closing,i+len(marker))
  while j>=0 and j and text[j-1]=='\\':j=text.find(closing,j+len(closing))
  end=len(text) if j<0 else j+len(closing);out.append((i,end));i=end
 return out

def new_context(text,tokens,index,homographs=()):
 ctx=guard.context(text,tokens,index,homographs);t=tokens[index]
 if any(a<t.end() and t.start()<b for a,b in quoted_ranges(text)):
  ctx['common_rejection']='protected_quoted_span'
 elif ctx['common_rejection']=='quoted_or_code_message':
  ctx['common_rejection']=None
  if t.group().isupper() and len(t.group())>1:ctx['common_rejection']='uppercase_identifier'
  elif t.group()[0].isupper() and not ctx['initial']:ctx['common_rejection']='mid_sentence_capital'
  elif t.group()[0].isupper() and t.group().casefold() in homographs:ctx['common_rejection']='attested_capitalized_homograph'
 return ctx

def summarize(rows):
 out=[]
 for key,m in rows.items():
  lang,arm,density,known,view=key;n=m['messages']
  out.append({'language':lang,'arm':arm,'density':density,'known':known,'view':view,**{k:v for k,v in m.items() if k not in {'concepts','depth_sum'}},'message_mean_content_depth':m['depth_sum']/n,'distinct_content_concepts':len(m['concepts']),'concepts':sorted(m['concepts'])})
 return out

def main():
 p=argparse.ArgumentParser();p.add_argument('--evidence-dir',type=Path,required=True);p.add_argument('--prepare-freeze',action='store_true');a=p.parse_args();E=a.evidence_dir;M=E/'scaled-mechanism-cases-r01';freeze=M/'editorial-guards-diagnostic-freeze-r02.json';output=M/'editorial-guards-diagnostic-output-r02.json'
 paths={'candidate':M/'editorial-content500-candidate-r01.json','train':E/'bst-evaluation-source-r01/train.json','source_inventory':E/'scaled-content-inventory-r01/source-inventory.json','baseline':Q/'content-expansion-candidate-r01.json','base_evaluator':Path(base.__file__),'base_guard':Path(guard.__file__),'runner':Path(__file__),'contrasts':Q/'editorial-content-contrasts-r01.json'}
 inventory=json.loads(paths['source_inventory'].read_text());noun_only={r['source'] for r in inventory['rows'] if set(r['parts_of_speech'])=={'noun'} and not r['mixed_content_function_or_name'] and r['content_lexemes']}
 if a.prepare_freeze:
  assert not freeze.exists();freeze.write_text(json.dumps({'production':False,'frozen_before_output':True,'inputs':{k:{'path':str(v),'sha256':sha(v)} for k,v in paths.items()},'arms':ARMS,'noun_only_sources':sorted(noun_only),'noun_only_basis':'Every complete source-form POS in the retained compiled English inventory is noun and no mixed function/name flag. No global all-senses agreement or semantic-accuracy assertion; unseen English roles can still exist.','literal_rule':'Protect complete balanced double/curly quotes and backtick code scopes; unmatched opener protects through message end. Outside those ranges retain current URL/identifier/capitalization guards. Single apostrophes remain contractions as in control.','other_changes':'None: exact candidate faces, primary proof defects, grouping, target reading, budget and selector remain frozen r01. Does not separately relax to: noun-only motion-to cases can pass but noun/verb alternatives keep current role requirement.','metrics':'All9535 TRAIN, densities10/25/50, knowledge none/all_function/global50/100/300, all/length bins. Raw gains are not correct coverage.','review_selection':'8 deterministic gain scopes per target per isolated mechanism scoped_literals/noun_only; root can review fixed48packet. Full gain contexts retained. Authored scope/boundary contrasts remain separate from corpus.'},ensure_ascii=False,indent=2)+'\n');print('freeze',sha(freeze),'noun_only',len(noun_only));return
 f=json.loads(freeze.read_text());assert not output.exists()
 for k,v in paths.items():assert sha(v)==f['inputs'][k]['sha256'],k
 candidate=json.loads(paths['candidate'].read_text());baseline=json.loads(paths['baseline'].read_text());train=json.loads(paths['train'].read_text());cases=[{'id':f'bst-train-{ci:04d}-{ti:02d}','text':text,'preceding_context_for_review_only':c['dialog'][:ti]} for ci,c in enumerate(train) if c['context_dataset']=='convai2' for ti,(speaker,text) in enumerate(c['dialog']) if speaker==0 and text.strip()];assert len(cases)==9535
 metrics={};gains=collections.defaultdict(list);old_context=base.context;old_eligible=base.eligible;started=time.monotonic();admissions=collections.Counter()
 def noun_eligible(ctx,pos,roles,form_kind='canonical'):
  if pos=='noun' and not ctx['common_rejection'] and ctx['word'] in noun_only:return True,'inventory_noun_only_role'
  return guard.eligible(ctx,pos,roles,form_kind)
 for case in cases:
  for lang in ['sw','ja','es']:
   controls=None
   for arm in ARMS:
    base.context=new_context if arm in {'scoped_literals','combined'} else old_context;base.eligible=noun_eligible if arm in {'noun_only','combined'} else old_eligible
    r=base.run(case['text'],baseline,candidate,lang);n=r['source_words']
    if arm=='control':controls=r
    for density in base.DENSITIES:
     for known in base.KNOWLEDGE:
      selection=r['arms'][f'editorial500|{density:.2f}|{known}']
      for view in ['all','length_'+('1-5' if n<=5 else '6-15' if n<=15 else '16+')]:
       k=(lang,arm,density,known,view);m=metrics.setdefault(k,{'messages':0,'content_available':0,'available':0,'content_changed_words':0,'source_words':0,'depth_sum':0.,'concepts':set()});m['messages']+=1;m['content_available']+=bool(selection['content_source_words']);m['available']+=bool(selection['spans']);m['content_changed_words']+=selection['content_source_words'];m['source_words']+=n;m['depth_sum']+=selection['content_source_words']/n if n else 0;m['concepts'].update(s['concept_id'] for s in selection['spans'] if s['category']=='content')
    if arm!='control':
     s=r['arms']['editorial500|0.25|none'];c=controls['arms']['editorial500|0.25|none'];existing={(x['start'],x['end'],x['lexicon_id']) for x in c['spans']};added=[x for x in s['spans'] if (x['start'],x['end'],x['lexicon_id']) not in existing]
     if added:gains[lang+'|'+arm].append({**case,'language':lang,'arm':arm,'source_words':n,'control25':c,'candidate25':s,'new_selected_scopes':added})
 base.context=old_context;base.eligible=old_eligible
 # Compact general structural probes independent of training, with no new targets.
 texts=['I said "hello" and enjoy music.','I said "music" and enjoy coffee.','I wrote `music()` and enjoy coffee.','I said "music and coffee.','I enjoy https://example.com/music and coffee.','My parents work nearby.','The company parents a subsidiary.','I go to school.','I want to work.','I brought books.']
 probes=[]
 for text in texts:
  tokens=list(WORD.finditer(text));probes.append({'text':text,'quoted_ranges':quoted_ranges(text),'tokens':[{'word':t.group(),'common_guard':new_context(text,tokens,i,candidate['capitalized_homographs'])['common_rejection'],'noun_only':t.group().casefold() in noun_only} for i,t in enumerate(tokens)]})
 packet=[]
 for lang in ['sw','ja','es']:
  for arm in ['scoped_literals','noun_only']:
   rows=sorted(gains[lang+'|'+arm],key=lambda r:hashlib.sha256(('vipi-guards-r02|'+lang+'|'+arm+'|'+r['id']).encode()).hexdigest())
   for r in rows[:8]:
    spans=sorted(r['new_selected_scopes'],key=lambda s:hashlib.sha256((r['id']+'|'+s['lexicon_id']+'|'+str(s['start'])).encode()).hexdigest());packet.append({**r,'selected_review_scope':spans[0]})
 out={'production':False,'provider_calls':0,'semantic_approval':False,'freeze_sha256':sha(freeze),'source_messages':len(cases),'noun_only_inventory_forms':len(noun_only),'summary':summarize(metrics),'all_gain_contexts':dict(gains),'fixed_review_packet':packet,'authored_structural_probes':probes,'elapsed_seconds':time.monotonic()-started,'limitations':['TRAIN diagnostic, not fresh holdout or native performance.','No changes to potentially wrong source senses/target faces; literal/role availability is not semantic correctness.','Inventory-only-noun is a source-role proxy from retained forms, not proof of no possible English use.','Existing starter producer may independently withhold candidates; scoped-literal arm relaxes only the added shared guard.']};output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'path':str(output),'sha256':sha(output),'seconds':out['elapsed_seconds'],'review_rows':len(packet),'gain_rows':{k:len(v) for k,v in gains.items()}}))
if __name__=='__main__':main()
