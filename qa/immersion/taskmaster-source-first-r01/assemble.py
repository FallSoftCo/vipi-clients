from pathlib import Path
import json,hashlib,collections
w=Path('/home/ai/Development/investigations/vipi-taskmaster-source-first-20261109-r01');old=w.parent/'vipi-target-informed-taskmaster-20261109-r01';load=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();digest=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def sub(t,r):return t.encode('utf-16-le')[r[0]*2:r[1]*2].decode('utf-16-le')
x=load(w/'run-r01/output.json');prior=load(old/'run-r02/output.json');inputs=load(w/'inputs-200.json');status=load(w/'cache-status.json');plan=load(w/'review-selection-freeze.json');byid={r['id']:r for r in prior['cases']};meta={r['id']:r for r in inputs['cases']};assert len(x['cases'])==200;assert x['known_family_ids']==[] and x['withhold_function']==False and x['density']==.25
packet=[];keys=[];metrics=collections.Counter();deltas=[]
for row in x['cases']:
 cid=row['id'];source=row['original'];oldrow=byid[cid];assert source==meta[cid]['text']==oldrow['original'];assert row['words']==oldrow['source_native_words'];assert row['source_masks']==oldrow['source_strict_masks'];assert row['source_protections']==oldrow['source_overlap_protections']
 spans=[]
 for i in row['selection']['selected_indices']:
  c=row['candidates'][i];assert sub(source,c['focus_utf16'])==c['source'];spans.append({'source':c['source'],'source_utf16':c['focus_utf16'],'target':c['target']})
 bs=[{k:s[k] for k in ['source','source_utf16','target']} for s in oldrow.get('aligned_spans_after_strict_snapshot_veto',[])];bs.sort(key=lambda s:s['source_utf16']);spans.sort(key=lambda s:s['source_utf16'])
 def mixed(ss):
  b=source.encode('utf-16-le')
  for s in sorted(ss,key=lambda s:s['source_utf16'],reverse=True):a,z=s['source_utf16'];b=b[:a*2]+s['target'].encode('utf-16-le')+b[z*2:]
  return b.decode('utf-16-le')
 assert mixed(spans)==row['selection']['mixed_output'];methods={'source_first':spans,'target_informed':bs};changed=spans!=bs;metrics['changed_cases']+=changed
 rows=[]
 for method in sorted(methods,key=lambda m:digest(['taskmaster-source-first-r01:labels',cid,m])):
  ss=methods[method];label=chr(88+len(rows));rows.append({'label':label,'mixed_output':mixed(ss),'spans':ss,'zero_immersion':not ss});keys.append({'id':cid,'label':label,'method':method});metrics[method+'_nonempty']+=bool(ss);metrics[method+'_spans']+=len(ss)
 packet.append({'id':cid,'source':source,'prior_dialogue':meta[cid]['prior_dialogue'],'options':rows,'changed_options':changed})
 a={digest(s):s for s in spans};b={digest(s):s for s in bs};deltas.append({'id':cid,'added_source_first':[a[k] for k in a.keys()-b.keys()],'lost_source_first':[b[k] for k in b.keys()-a.keys()]})
changed={r['id'] for r in packet if r['changed_options']};subset=[i for i in plan['all_ids_in_priority_order'] if i in changed][:40];out=w/'packet';out.mkdir(exist_ok=False)
for n,data in [('anonymous-all200.json',{'cases':packet,'exposure':'Existing target-informed outputs previously reviewed; new source-first outputs. Method key not read for this review; historical method inference may be possible.'}),('anonymous-root40.json',{'cases':[next(r for r in packet if r['id']==i) for i in subset]}),('method-key.json',keys),('deltas.json',deltas),('metrics.json',dict(metrics)),('selection.json',{'ids':subset,'predeclared_order_sha256':sha(w/'review-selection-freeze.json'),'changed_cases':len(changed),'no_quality_selection':True})]:(out/n).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
(out/'receipt.json').write_text(json.dumps({'source_output_sha256':sha(w/'run-r01/output.json'),'prior_output_sha256':sha(old/'run-r02/output.json'),'files':{p.name:sha(p) for p in out.iterdir()}},indent=2)+'\n');print('anonymous-root40',sha(out/'anonymous-root40.json'));print('anonymous-all200',sha(out/'anonymous-all200.json'))
