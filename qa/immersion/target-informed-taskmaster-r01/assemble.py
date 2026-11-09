"""Assemble fixed anonymous packet; no selection based on observed changes."""
import pathlib,json,hashlib,collections
W=pathlib.Path('/home/ai/Development/investigations/vipi-target-informed-taskmaster-20261109-r01');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();enc=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'));h=lambda s:hashlib.sha256(s.encode()).hexdigest()
j=json.loads((W/'run-r02/output.json').read_text());freeze=json.loads((W/'selection-freeze.json').read_text());inputs=json.loads((W/'inputs-200.json').read_text());meta={x['id']:x for x in inputs['cases']};fids=[x['id'] for x in freeze['cases']];assert [x['id'] for x in j['baseline']]==fids==[x['id'] for x in j['cases']]
subset={x['id'] for x in freeze['root_review_subset']};packet=[];key=[];deltas=[];witnesses=[];metrics=collections.Counter();times={};proof=collections.Counter()
def mixed(text,spans):
 raw=text.encode('utf-16-le')
 for s in sorted(spans,key=lambda x:x['source_utf16'][0],reverse=True):
  a,b=s['source_utf16'];assert text.encode('utf-16-le')[2*a:2*b].decode('utf-16-le')==s['source'];raw=raw[:2*a]+s['target'].encode('utf-16-le')+raw[2*b:]
 return raw.decode('utf-16-le')
for a,b in zip(j['baseline'],j['cases']):
 ident=a['id'];text=a['original'];assert text==b['original'];options=[];arms={};audit={}
 for method,row in [('A',a),('B',b)]:
  spans=row.get('aligned_spans_after_strict_snapshot_veto',[]);arms[method]=spans;metrics[method+'_nonempty']+=bool(spans);metrics[method+'_spans']+=len(spans);metrics[method+'_null_provider']+=row.get('abstention')=='provider_missing_target';metrics[method+'_other_abstention']+=bool(row.get('abstention')) and row.get('abstention')!='provider_missing_target'
  wordranges=row['source_native_words'];metrics[method+'_source_words']+=len(wordranges);metrics[method+'_changed_words']+=sum(any(x<=u and v<=y for s in spans for x,y in [s['source_utf16']]) for u,v in wordranges)
  if 'alignment_elapsed_ns' in row:times.setdefault(method,[]).append({'id':ident,'ns':row['alignment_elapsed_ns']})
  for s in spans:
   u,v=s['target_utf16'];assert row['translation'].encode('utf-16-le')[2*u:2*v].decode('utf-16-le')==s['target']
  label=('X' if method=='A' else 'Y') if int(h(freeze['label_assignment_seed']+'\0'+ident)[0],16)%2==0 else ('Y' if method=='A' else 'X')
  options.append({'label':label,'mixed':mixed(text,spans),'spans':spans,'zero_immersion':not bool(spans),'abstention':row.get('abstention'),'provider_error':row.get('provider_error')});key.append({'id':ident,'label':label,'method':method})
  if method=='B':
   ds=row.get('lexical_diagnostics_aggregate_not_focus_labels',{});owners=[]
   for k,n in ds.items():
    if k.startswith('target_graph:'):
     item=json.loads(k[13:]);proof[item['kind']]+=n
     if item['kind']=='ownership':owners.append(item)
   proof['maximum_graph_edges']=max(proof['maximum_graph_edges'],len(owners));proof['ownership_controls_passes']+=ds.get('target_graph_ownership_controls_passed',0)
 old=set(map(enc,arms['A']));new=set(map(enc,arms['B']));added=[s for s in arms['B'] if enc(s) not in old];lost=[s for s in arms['A'] if enc(s) not in new];metrics['added_spans']+=len(added);metrics['lost_spans']+=len(lost);metrics['changed_messages']+=old!=new;metrics['empty_gain']+=not old and bool(new);metrics['empty_loss']+=bool(old) and not new
 packet.append({'id':ident,'original':text,'prior_dialogue':meta[ident]['prior_dialogue'],'root_subset':ident in subset,'options':sorted(options,key=lambda x:x['label'])});deltas.append({'id':ident,'added':added,'lost':lost,'A_mixed':mixed(text,arms['A']),'B_mixed':mixed(text,arms['B'])});witnesses.append({'id':ident,'target':b.get('translation'),'source_masks':b['source_strict_masks'],'overlap_protections':b['source_overlap_protections'],'raw_result_index':len(witnesses)})
assert len(packet)==200;out=W/'packet';out.mkdir(exist_ok=False)
files={'anonymous-all200.json':{'rubric':'Agent diagnostic: correct/minor_issue/material_error/uncertain. Preserve source grammar; assess meaning/form/scope. Empty is unavailable, zero useful immersion. No full target references here.','cases':packet},'anonymous-root40.json':{'selection_sha256':sha(W/'selection-freeze.json'),'cases':[x for x in packet if x['id'] in subset]},'method-key.json':key,'parallel-witnesses.json':witnesses,'deltas.json':deltas,'metrics.json':{'rows':200,'unique_sources':185,'counts':dict(metrics),'graph':dict(proof),'timings_ns':times,'timing_interpretation':'First invocation and subsequent same actor cases; A runs before B. OS/model caches not reset; no same-input warm repetition, no translation timing.'}}
for n,v in files.items():(out/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
(out/'receipt.json').write_text(json.dumps({'source_result_sha256':sha(W/'run-r02/output.json'),'selection_sha256':sha(W/'selection-freeze.json'),'files':{n:sha(out/n) for n in files},'semantic_labels_not_written':True},indent=2)+'\n');print(json.dumps({'packet_sha256':sha(out/'anonymous-all200.json'),'root40_sha256':sha(out/'anonymous-root40.json'),'counts':dict(metrics),'graph':dict(proof)}))
