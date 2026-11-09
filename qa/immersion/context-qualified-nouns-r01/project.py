"""Exact control replay before gated predictions; no new inference or targets."""
from common import *

def annotation_loader(path):
 tree=ast.parse(pathlib.Path(path).read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='annotations');env={'json':json,'hashlib':hashlib};exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),env);return env['annotations']

def gate(trace,lookup,tok):
 text=trace['text'];off=[0]
 for ch in text:off.append(off[-1]+len(ch.encode('utf-16-le'))//2)
 tokens=tok(text);values=[norm(t[0]) for t in tokens];ranges={(off[a],off[b]):i for i,(_,a,b) in enumerate(tokens)};native={tuple(v) for v in trace['native_words_utf16']};groups=collections.defaultdict(list);n=trace['baseline_candidate_count'];decisions={};keep=[]
 for i,c in enumerate(trace['candidates'][n:],n):
  if c['filter_reasons']:continue
  assert c['role']['raw'][0]=='NOUN' and c['source'].islower() and c['category']=='content' and c['cost']==1
  groups[tuple(c['focus_utf16'])].append(i)
 for focus,indices in groups.items():
  pos=ranges.get(focus);matches=[];tested=set()
  if pos is not None:
   keys={k for i in indices for k in lookup['head_keys'].get(trace['candidates'][i]['head_id'],[])}
   for key in keys:
    assert json.loads(key)[0]==norm(trace['candidates'][indices[0]]['source'])
    for rulekey,a,b in windows(key,values,pos):
     if rulekey in tested:continue
     tested.add(rulekey)
     # Exact corpus tokens must each be native words; punctuation remains in tokens and is a barrier.
     if any((off[tokens[j][1]],off[tokens[j][2]]) not in native for j in range(a,b)):continue
     rule=lookup['rules'].get(rulekey)
     if rule:matches.append({'rule':rule,'tokens':[a,b],'utf16':[off[tokens[a][1]],off[tokens[b-1][2]]]})
  matches.sort(key=rank_rule);chosen=matches[0] if matches else None;admitted=[]
  if chosen:
   rule=chosen['rule']
   for i in indices:
    c=trace['candidates'][i]
    if c['target']==rule['target'] and c['head_id'] in rule['admissible_head_rows']:admitted.append(i)
   # A supported winner with no eligible current head (or same-source face) gets no alternate rescue.
  keep.extend(admitted);decisions[enc(focus)]={'candidate_indices':indices,'admitted_indices':admitted,'chosen_rule_id':chosen['rule']['id'] if chosen else None,'chosen_context_utf16':chosen['utf16'] if chosen else None,'chosen_source_tokens':chosen['tokens'] if chosen else None,'matched_rules':[{'id':m['rule']['id'],'tokens':m['tokens'],'utf16':m['utf16'],'target':m['rule']['target']} for m in matches],'reason':'qualified_context' if admitted else 'winner_without_original_supported_head' if chosen else 'no_qualified_multiword_context'}
 return sorted(keep),decisions

def mechanism_controls(selector,tok):
 def c(ident,focus,word):return {'id':ident,'head_id':ident,'focus_utf16':focus,'context_utf16':focus,'source':word,'target':'target-'+ident,'reading':[],'identical_face':False,'category':'content','concept_id':ident,'knowledge_ids':[ident],'train_rank':0,'cost':1,'role':{'raw':['NOUN',1.0]},'filter_reasons':[]}
 t={'text':'red title safe','native_words_utf16':[[0,3],[4,9],[10,14]],'source_masks':[{'unit_id':'title-enclosure','utf16':[0,9]}],'protected_ranges_utf16':[],'baseline_candidate_count':2,'candidates':[c('ordinary',[4,9],'title'),c('safe',[10,14],'safe'),c('exception',[4,9],'title')]}
 keep,audit=gate(t,{'rules':{},'head_keys':{}},tok);assert keep==[];masks=digest(t['source_masks']);out=translated(selector,t,[0,1]+keep,'all_function',[]);assert out['selected_indices']==[1] and 'inside_recognized_source_unit' in out['rejected'][0]['reasons'] and digest(t['source_masks'])==masks
 return {'functional_mask_survives_absent_exception':True,'no_unigram_fallback':True,'punctuation_and_apostrophe_controls':controls(tok)}

def main(r):
 r.verify();prepared=r.prior('prepare');lookup=json.loads((prepared/'lookup.json').read_text());selector=load('frozen_selector',r.paths['selector']);order=json.loads(r.paths['family_control'].read_text())['learned_family_order'];assert mechanism_controls(selector,r.tokenize);sources={x['id']:x['text'] for x in json.loads(r.paths['annotation_inputs'].read_text())['cases']};annotations=annotation_loader(r.paths['annotation_loader'])(r.paths['annotations'],'opennlp',sources);seen=[];parityhash=hashlib.sha256()
 # Full two-pass discipline: no gated selections before all9535x2 baseline/control comparisons pass.
 with gzip.open(r.paths['trace'],'rt') as f:
  for line in f:
   t=json.loads(line);assert sources[t['id']]==t['text'];seen.append(t['id']);assert not t['competition_removed_baseline_indices'];n=t['baseline_candidate_count'];cs=t['candidates'];base=[i for i,c in enumerate(cs[:n]) if not c['filter_reasons']];control=[i for i,c in enumerate(cs) if not c['filter_reasons']]
   for c in cs:
    raw=annotations[t['id']].get(tuple(c['focus_utf16']));assert (list(raw) if raw else None)==c['role']['raw']
   for known in KNOWN:
    assert translated(selector,t,base,known,order)==t['decisions'][known]['baseline'],(t['id'],known,'baseline')
    assert translated(selector,t,control,known,order)==t['decisions'][known]['experimental'],(t['id'],known,'unrestricted')
   parityhash.update(enc(t['decisions']).encode())
 assert seen==list(sources) and len(seen)==9535;r.write('baseline-control-parity.json',{'complete':True,'messages':9535,'states':KNOWN,'full_decision_fields_equal':True,'live_annotation_range_binding_equal':True,'mask_policy':'Exact retained enclosing-unit masks and protected ranges reused even with no gated candidate','decision_stream_sha256':parityhash.hexdigest(),'before_new_selections':True})
 exclusion=json.loads(r.paths['review_exclusions'].read_text());exids=set(exclusion['source_ids']);exhash=set(exclusion['hashes']);pools=collections.defaultdict(list);sample_counts=collections.Counter();metrics=collections.defaultdict(collections.Counter);paired=collections.defaultdict(collections.Counter);fout=gzip.open(r.out/'decisions.jsonl.gz','xb',compresslevel=6);bytes_raw=0;gating=collections.Counter()
 try:
  with gzip.open(r.paths['trace'],'rt') as f:
   for line in f:
    t=json.loads(line);cs=t['candidates'];n=t['baseline_candidate_count'];base=[i for i,c in enumerate(cs[:n]) if not c['filter_reasons']];before=digest([t['source_masks'],t['protected_ranges_utf16']]);keep,audit=gate(t,lookup,r.tokenize);gating.update(v['reason'] for v in audit.values());arms={}
    for known in KNOWN:
     q=translated(selector,t,base+keep,known,order);assert digest([t['source_masks'],t['protected_ranges_utf16']])==before;arms[known]={'baseline':t['decisions'][known]['baseline'],'unrestricted':t['decisions'][known]['experimental'],'qualified':q};sig=lambda d:{enc([cs[i]['focus_utf16'],cs[i]['target'],cs[i]['reading']]) for i in d['selected_indices']};depth=lambda d:sum(cs[i]['cost'] for i in d['selected_indices']);b=arms[known]['baseline'];u=arms[known]['unrestricted'];ss=sig(q);bs=sig(b);us=sig(u)
     for name,d in arms[known].items():
      m=metrics[known+'|'+name];words=depth(d);m['messages']+=1;m['nonempty']+=bool(d['selected_indices']);m['emitted_words']+=words;m['native_words']+=len(t['native_words_utf16']);m['depth_zero']+=not words
      for threshold in [10,25,50]:m['depth_ge_'+str(threshold)]+=bool(t['native_words_utf16']) and 100*words>=threshold*len(t['native_words_utf16'])
     for other,osig,d in [('baseline',bs,b),('unrestricted',us,u)]:
      m=paired[known+'|qualified_vs_'+other];m['changed_messages']+=ss!=osig or q['mixed_output']!=d['mixed_output'];m['new_emissions']+=len(ss-osig);m['lost_emissions']+=len(osig-ss);m['empty_gains']+=not osig and bool(ss);m['empty_losses']+=bool(osig) and not ss;m['depth_gain_messages']+=depth(q)>depth(d);m['depth_loss_messages']+=depth(q)<depth(d)
     stratum='loss' if depth(q)<depth(b) else 'empty_gain' if not bs and ss else 'nonempty_change' if ss!=bs or q['mixed_output']!=b['mixed_output'] else 'withheld_exception' if ss!=us or q['mixed_output']!=u['mixed_output'] else 'control';sample_counts[known+'|'+stratum]+=1
     fingerprint=hashlib.sha256(('en\0'+norm(t['text'])).encode()).hexdigest()
     if t['id'] in exids or fingerprint in exhash:continue
     rank=digest(['context-qualified-nouns-r01',stratum,known,t['id']]);pools[(stratum,known)].append((rank,t['id']))
    v={'id':t['id'],'gates':audit,'qualified':{k:arms[k]['qualified'] for k in KNOWN},'retained_trace_sha256':r.p['inputs']['trace']['sha256']};raw=(enc(v)+'\n').encode();bytes_raw+=len(raw);assert bytes_raw<64*M,'prospective compact uncompressed decision cap';fout.write(raw)
 finally:fout.close()
 selected=[];used=set();quotas=[('loss',2),('empty_gain',4),('nonempty_change',4),('withheld_exception',4),('control',2)];anychanged=any(v for k,v in sample_counts.items() if not k.endswith('|control'))
 for stratum,quota in quotas:
  for known in KNOWN:
   if stratum=='control' and not anychanged:continue
   chosen=0
   for rank,ident in sorted(pools[stratum,known]):
    if ident in used:continue
    selected.append({'id':ident,'known':known,'stratum':stratum,'rank':rank});used.add(ident);chosen+=1
    if chosen==quota:break
 r.write('metrics.json',{'arms':{k:dict(v) for k,v in metrics.items()},'paired':{k:dict(v) for k,v in paired.items()},'gating':dict(gating),'depth_is_emitted_words_not_context_length':True,'semantic_acceptance_not_inferred':True,'uncompressed_decision_bytes':bytes_raw});r.write('review-selection-freeze.json',{'selected':selected,'stratum_counts':dict(sample_counts),'development_source_ids':r.p['development_source_ids'],'no_backfill':True,'quotas_each_state':dict(quotas),'exclusions_sha256':r.p['inputs']['review_exclusions']['sha256'],'anonymous_packet_separate_from_witnesses':True})
if __name__=='__main__':
 r=Run('project')
 try:main(r);r.finish()
 except BaseException as e:r.finish(repr(e));raise
