"""Join frozen independent agent judgments without rewriting either review."""
import pathlib,json,hashlib,collections,statistics,datetime
W=pathlib.Path('/home/ai/Development/investigations/vipi-target-informed-taskmaster-20261109-r01');read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();canon=lambda x:json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'))
a=read(W/'author-review-r01.json');r=read(W/'root-masked-review-r01.json');assert sha(W/'author-review-r01.json')=='c848b0d16c9c17ffcd2d6005b41fa51ccd68bb0b64d05de3ed096b2659d5c0e8';assert sha(W/'root-masked-review-r01.json')=='87299d778185a65d13a6e4aab3ef997a2b17570ed38f90332df7fd03827f893d'
key={(x['id'],x['label']):x['method'] for x in read(W/'packet/method-key.json')};allrows=read(W/'packet/anonymous-all200.json')['cases'];byid={x['id']:x for x in allrows};src=read(W/'run-r02/output.json');geometry={x['id']:x['source_native_words'] for x in src['cases']}
assert len(a['options'])==400 and len(r['rows'])==40
stats=collections.defaultdict(collections.Counter);author={};root={};joined=[];disagreements=[]
for x in a['options']:
 k=(x['id'],x['option']);method=key[k];author[k]=x;stats['author_all200|'+method][x['label']]+=1
for row in r['rows']:
 for o in row['options']:
  k=(row['id'],o['label']);assert k in author;root[k]=o;method=key[k];norm={'minor_form':'minor_issue','empty':'unavailable'}.get(o['judgment'],o['judgment']);stats['root40|'+method][norm]+=1;stats['author_same40|'+method][author[k]['label']]+=1
  v={'id':k[0],'option':k[1],'method':method,'root_raw':o,'author_raw':author[k],'normalized_root':norm,'normalized_author':author[k]['label']};joined.append(v)
  if norm!=author[k]['label']:disagreements.append(v)
# Added/lost lexical events are matched by exact span identity, not candidate index.
events=[];eventstats=collections.defaultdict(collections.Counter)
for row in allrows:
 mapping={key[(row['id'],o['label'])]:author[(row['id'],o['label'])] for o in row['options']};units={m:{canon(u['span']):u for u in x['units']} for m,x in mapping.items()}
 for side,frm,to in [('added','A','B'),('lost','B','A')]:
  for s in sorted(set(units[to])-set(units[frm])):
   u=units[to][s];eventstats[side][u['label']]+=1;events.append({'id':row['id'],'event':side,'method':to,'unit':u})
paired=collections.defaultdict(collections.Counter)
for scope,records in [('author_all200',author),('root40',root)]:
 ids={k[0] for k in records}
 for ident in ids:
  labels={key[k]:({'minor_form':'minor_issue','empty':'unavailable'}.get(v['judgment'],v['judgment']) if scope=='root40' else v['label']) for k,v in records.items() if k[0]==ident}
  for name,good in [('strict',{'correct'}),('minor_tolerant',{'correct','minor_issue'})]:
   before=labels['A'] in good;after=labels['B'] in good;paired[scope+'|'+name]['gained']+=not before and after;paired[scope+'|'+name]['lost']+=before and not after
  paired[scope]['material_introduced']+=labels['A']!='material_error' and labels['B']=='material_error';paired[scope]['material_removed']+=labels['A']=='material_error' and labels['B']!='material_error'
# Whole-message accepted depth versus per-unit depth kept distinct.
depth=collections.defaultdict(collections.Counter)
for k,x in author.items():
 method=key[k];ranges=geometry[k[0]];d=depth[method];d['native_words']+=len(ranges)
 for mode,good in [('strict',{'correct'}),('minor_tolerant',{'correct','minor_issue'})]:
  spans=[u['span'] for u in x['units'] if u['label'] in good];d[mode+'_accepted_unit_words']+=sum(any(s['source_utf16'][0]<=u and v<=s['source_utf16'][1] for s in spans) for u,v in ranges)
  if x['label'] in good:d[mode+'_clean_whole_output_words']+=sum(any(s['span']['source_utf16'][0]<=u and v<=s['span']['source_utf16'][1] for s in x['units']) for u,v in ranges)
m=read(W/'packet/metrics.json');timing={}
for method,vals in m['timings_ns'].items():
 ns=[x['ns'] for x in vals];rest=ns[1:];timing[method]={'first_case_id':vals[0]['id'],'first_ms':ns[0]/1e6,'subsequent_count':len(rest),'subsequent_median_ms':statistics.median(rest)/1e6,'subsequent_max_ms':max(rest)/1e6,'total_alignment_ms':sum(ns)/1e6,'not_same_input_warm_repeat':True,'B_runs_after_A':True}
result={'review_hashes':{'author':sha(W/'author-review-r01.json'),'root':sha(W/'root-masked-review-r01.json')},'counts':{k:dict(v) for k,v in stats.items()},'paired':{k:dict(v) for k,v in paired.items()},'added_lost_author_unit_labels':{k:dict(v) for k,v in eventstats.items()},'author_depth':{k:dict(v) for k,v in depth.items()},'timings':timing,'joined_root40':joined,'disagreements':disagreements,'all_emission_events':events,'interpretation':'Independent agent judgments, no majority gold; all200 historical diagnostics and root40 source-only presample. Empty unavailable. Normalization changes label spelling only.'}
(W/'joined-review-r01.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
exposure={'author_file_mtime_utc':datetime.datetime.fromtimestamp((W/'author-review-r01.json').stat().st_mtime,datetime.timezone.utc).isoformat(),'author_sha256':sha(W/'author-review-r01.json'),'root_file_frozen_at':r['frozen_at_utc'],'message_visibility':'Root example-judgment message first became model-visible after author freeze tool returned SHA and after author freeze notification. Author judgments were already in the tool-call source. Root file timestamp is earlier, not proof of reviewer exposure.','transport_receipt_timestamp_available':False,'labels_modified_after_root_message':False,'method_key_and_root_file_read_only_after_author_freeze':True};(W/'review-exposure-receipt.json').write_text(json.dumps(exposure,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k in ['counts','paired','added_lost_author_unit_labels','author_depth','timings']},indent=2));print('disagreements',[(x['id'],x['option'],x['normalized_author'],x['normalized_root']) for x in disagreements])
