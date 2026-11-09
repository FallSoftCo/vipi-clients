from pathlib import Path
import json,collections,statistics,hashlib
w=Path('/home/ai/Development/investigations/vipi-taskmaster-source-first-20261109-r01');load=lambda p:json.loads(p.read_text());x=load(w/'run-r01/output.json');status=load(w/'cache-status.json');delta=load(w/'packet/deltas.json');counts=collections.Counter();reasons=collections.Counter();per=[]
for row in x['cases']:
 sel=row['selection'];selected=sel['selected_indices'];cs=row['candidates'];stage='nonempty'
 if not selected:
  if not cs:stage='no_candidate_records'
  elif not row['qualified_indices_before_current_evidence']:stage='no_qualified_candidates_before_current_tuple'
  elif not row['qualified_indices']:stage='all_withheld_by_current_tuple'
  elif not sel['pre_budget_indices']:stage='all_selector_input_rejected'
  else:stage='selection_budget_or_competition'
 counts[stage]+=1;counts['candidates']+=len(cs);counts['ordinary_candidates']+=row['ordinary_count'];counts['conditional_candidates']+=len(cs)-row['ordinary_count'];counts['selected_spans']+=len(selected);counts['gates']+=len(row['gates']);counts['native_words']+=len(row['words'])
 words=set()
 for i in selected:
  f=cs[i]['focus_utf16'];covered=[tuple(r) for r in row['words'] if f[0]<=r[0] and r[1]<=f[1]];assert len(covered)==cs[i]['cost'];words.update(covered)
 counts['selected_words']+=len(words)
 cr=collections.Counter(reason for c in cs for reason in c['filter_reasons']);sr=collections.Counter(reason for reject in sel['rejected'] for reason in reject['reasons']);reasons.update(cr);reasons.update(sr)
 per.append({'id':row['id'],'cache_status':status[row['id']],'empty_stage':stage,'candidates':len(cs),'qualified_before_current':len(row['qualified_indices_before_current_evidence']),'qualified_current':len(row['qualified_indices']),'selected_spans':len(selected),'selected_words':len(words),'overlapping_candidate_filter_reasons':dict(cr),'overlapping_selection_reasons':dict(sr),'geometry_rejections':len(row['geometry_rejections']),'conditional_geometry_rejections':len(row['conditional_geometry_rejections'])})
receipt=load(w/'run-r01/receipt.json');times={k:[r[k]/1e6 for r in x['cases']] for k in ['prepare_ns','select_ns']};r={'counts':dict(counts),'empty_stages_are_exclusive':True,'reason_counts_overlap':dict(reasons),'cases':per,'known_ids':x['known_family_ids'],'withhold_function':x['withhold_function'],'null_cache_cases':sum(s=='INVALID_LANGUAGE' for s in status.values()),'null_cache_nonempty':sum(r['cache_status']=='INVALID_LANGUAGE' and r['selected_spans']>0 for r in per),'added_spans':sum(len(d['added_source_first']) for d in delta),'lost_spans':sum(len(d['lost_source_first']) for d in delta),'timing_ms':{k:{'first':v[0],'subsequent_median':statistics.median(v[1:]),'maximum':max(v),'sum':sum(v)} for k,v in times.items()},'identity_init_ms':x['identity_preparation_ns']/1e6,'serialization':load(w/'run-r01/timing.json'),'native_stage_seconds':{s['name']:s['seconds'] for s in receipt['stages']},'process_memory_claim':None,'state_closure':receipt['state_closure'],'output_sha256':hashlib.sha256((w/'run-r01/output.json').read_bytes()).hexdigest()};(w/'mechanics.json').write_text(json.dumps(r,indent=2)+'\n');print('mechanics retained; no semantic output')
