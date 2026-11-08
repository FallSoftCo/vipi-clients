#!/usr/bin/env python3
"""Deterministic whole-output review packet, preserving every selected scope."""
import collections,gzip,hashlib,json,pathlib
from project import ARM_NAMES,choose,encoded,norm,role,sha,write

class Selection:
 def __init__(self,policy,bindings,sources):
  self.policy=policy;self.bindings=bindings;self.sources=sources;self.pools=collections.defaultdict(list);self.counts=collections.Counter();self.exclusions=collections.Counter()
  prior=json.loads(pathlib.Path(bindings['prior96_packet']['path']).read_text());self.prior_ids={c['case_id'] for c in prior['cases']}
  self.hashes=set(json.loads(pathlib.Path(bindings['prior_evaluated_source_hashes']['path']).read_text())['hashes'])
 def consider(self,ident,pair,known,byarm,cmap):
  if known not in self.policy['known']:return
  if ident in self.prior_ids:self.exclusions['prior96_case_records']+=1;return
  fingerprint=hashlib.sha256(('en\0'+norm(self.sources[ident])).encode()).hexdigest()
  if fingerprint in self.hashes:self.exclusions['evaluated_source_fingerprint_records']+=1;return
  ids={a:tuple(cmap[i]['id'] for i in byarm[a]['selected_indices']) for a in ARM_NAMES};control=ids['eligible_links']
  veto=ids['apple_disagreement_veto']!=control or ids['opennlp_disagreement_veto']!=control
  predicates={'role_veto_delta':veto,'role_required_only_delta':not veto and (ids['apple_role_required']!=control or ids['opennlp_role_required']!=control),'eligibility_delta':ids['original']!=control and not veto,'unchanged_control':len(set(ids.values()))==1 and any(cmap[i]['category']=='content' for i in byarm['original']['selected_indices'])}
  for stratum,yes in predicates.items():
   if not yes:continue
   key=(stratum,pair,known);self.counts['|'.join(key)]+=1;rank=hashlib.sha256(('|'.join([self.policy['seed'],stratum,pair,known,ident])).encode()).hexdigest()
   pool=self.pools[key];pool.append((rank,ident));pool.sort();del pool[self.policy['count_max']+2:]
 def freeze(self,out):
  chosen=[];seen=set();shortages=[]
  for stratum in self.policy['ordered_strata']:
   for pair in self.policy['pairs']:
    for known in self.policy['known']:
     picked=0
     for rank,ident in self.pools[stratum,pair,known]:
      if ident in seen:continue
      chosen.append(dict(source_id=ident,stratum=stratum,pair=pair,known=known,sampling_hash=rank));seen.add(ident);picked+=1
      if picked==self.policy['quota_per_stratum_pair_known']:break
     if picked<self.policy['quota_per_stratum_pair_known']:shortages.append(dict(stratum=stratum,pair=pair,known=known,selected=picked,quota=self.policy['quota_per_stratum_pair_known']))
  assert len(chosen)<=self.policy['count_max'] and len(seen)==len(chosen)
  result={'production':False,'semantic_labels_present':False,'before_target_bearing_packet':True,'selected':chosen,'stratum_population_records':dict(self.counts),'shortages':shortages,'exclusion_record_counts':dict(self.exclusions),'policy_sha256':sha(pathlib.Path(__file__).parent/'review-selection.json'),'decisions_sha256':sha(out/'decisions.jsonl.gz'),'retained_pool_bound':'First34 per bucket suffice: max32 globally unique sources; exact ordered quotas with no backfill.'}
  write(out/'review-selection-freeze.json',result);return result

def mixed(text,selected):
 raw=text.encode('utf-16-le')
 for c in sorted(selected,key=lambda x:x['focus_utf16'][0],reverse=True):
  a,b=c['focus_utf16'];raw=raw[:2*a]+c['target'].encode('utf-16-le')+raw[2*b:]
 return raw.decode('utf-16-le')

def packet(out,selection,cache,decision_path,metas,annotations,protocol,bindings,selector,order):
 wanted={r['source_id']:r for r in selection['selected']};retained={};decisions={}
 with gzip.open(cache,'rt') as f:
  for line in f:
   row=json.loads(line)
   if row['id'] in wanted:retained[row['id']]=row
 with gzip.open(decision_path,'rt') as f:
  for line in f:
   row=json.loads(line)
   if row['id'] in wanted:decisions[row['id']]=row
 # Read full supplied prior dialogue only after source selection is frozen.
 conversations=json.loads(pathlib.Path(bindings['source_context']['path']).read_text());prior={}
 for ident in wanted:
  _,_,ci,ti=ident.split('-');conversation=conversations[int(ci)];turn=int(ti)
  assert conversation['context_dataset']=='convai2'
  speaker,text=conversation['dialog'][turn];assert speaker==0 and text==retained[ident]['text']
  prior[ident]=conversation['dialog'][:turn]
 del conversations
 cases=[]
 for ordinal,selected in enumerate(selection['selected'],1):
  ident=selected['source_id'];pair=selected['pair'];known=selected['known'];row=retained[ident];data=row['pairs'][pair];candidates=data['candidates'];cmap=dict(candidates);statuses=decisions[ident]['pairs'][pair]['candidate_decisions'];records=decisions[ident]['pairs'][pair]['decisions'][known];arms={};union={}
  for arm in ARM_NAMES:
   members=[];filtered=[]
   for i,c in candidates:
    meta=metas[c['catalog_id']];evidence={e:role(c,meta,annotations[e][ident],protocol['POS_map'][e]) for e in ['apple','opennlp']};accept=arm=='original' or meta['eligible']
    reason='metadata_ineligible' if not accept else None
    if accept and arm not in ['original','eligible_links']:
     engine=arm.split('_')[0];status=evidence[engine]['status'];accept=status!='conflict' if arm.endswith('disagreement_veto') else status=='compatible'
     if not accept:reason='source_role_conflict' if status=='conflict' else 'source_role_unassessed'
    if accept:members.append((i,c))
    else:filtered.append({'index':i,'reason':reason})
   result=choose(selector,members,row['native_words_utf16'],row['protected_ranges_utf16'],row['source_masks'],known,order)
   assert result['selected_indices']==records[arm]['selected_indices']
   selected_candidates=[cmap[i] for i in result['selected_indices']]
   arms[arm]={'selected_indices':result['selected_indices'],'selected_candidate_ids':[c['id'] for c in selected_candidates],'mixed_output':mixed(row['text'],selected_candidates),'filter_rejected':filtered,'selector_decision':result}
   for i in result['selected_indices']:
    c=cmap[i];identity=encoded([c['focus_utf16'],c['target'],c['reading']])
    if identity not in union:union[identity]={'focus_utf16':c['focus_utf16'],'target':c['target'],'reading':c['reading'],'candidate_indices':[],'candidate_ids':[],'arms':[]}
    u=union[identity]
    if i not in u['candidate_indices']:u['candidate_indices'].append(i);u['candidate_ids'].append(c['id'])
    if arm not in u['arms']:u['arms'].append(arm)
  cases.append({'review_id':f'role-veto-{ordinal:03d}',**selected,'source':row['text'],'review_only_preceding_context':prior[ident],'native_words_utf16':row['native_words_utf16'],'source_masks':row['source_masks'],'protected_ranges_utf16':row['protected_ranges_utf16'],'candidates':[{'original_trace_index':i,'candidate':c,'eligibility_and_role':statuses[str(i)],'catalog_link_evidence':metas[c['catalog_id']]} for i,c in candidates],'arms':arms,'review_union':list(union.values()),'review_limits':'Review every emitted union focus/target and each whole arm output; unchanged means no evidence of semantic approval. Historical masks/weaknesses remain. No labels supplied.'})
 write(out/'review-packet.json',{'schema':'vipi.source-role-whole-output-review-packet.r01','production':False,'semantic_labels_present':False,'selection_sha256':sha(out/'review-selection-freeze.json'),'source_context_sha256':bindings['source_context']['sha256'],'cases':cases})
