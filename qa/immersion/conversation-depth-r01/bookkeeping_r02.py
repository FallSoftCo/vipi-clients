#!/usr/bin/env python3
"""Read-only mechanical census; no semantic grading or candidate rerun."""
from pathlib import Path
import json,hashlib,collections,statistics
W=Path('/home/ai/Development/investigations/vipi-conversation-depth-20261109-r01')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'android-bookkeeping-r02.json';assert not out.exists();inputs=W/'inputs/messages.json';raw=W/'android-capture-r01/output.stdout'
 cases={x['id']:x for x in json.loads(inputs.read_text())['cases']};rows=[json.loads(x)for x in raw.read_text().splitlines()];assert len(rows)==320
 expected={(id,'en-'+t,d)for id in cases for t in ['ja','sw']for d in [.25,.75]};seen=set();groups={};latency=[]
 for n,x in enumerate(rows):
  key=(x['id'],x['pair'],x['density']);assert key in expected and key not in seen;seen.add(key);c=cases[x['id']];assert x['source']==c['source'] and x['stratum']==c['stratum'];assert x['known_ids']==[]
  assert x['actual_default_factory'] and not x['provider_target_spans_injected'] and x['translation_calls']==0
  encoded=x['source'].encode('utf-16-le');words=x['native_words'];spans=x['spans'];end=0
  for a,b in words:assert 0<=a<b<=len(encoded)//2 and a>=end;encoded[a*2:b*2].decode('utf-16-le');end=b
  end=0;script=[];reading=[]
  for s in spans:
   a,b=s['source_utf16'];assert 0<=a<b<=len(encoded)//2 and a>=end and encoded[a*2:b*2].decode('utf-16-le')==s['source'];prefix=encoded[end*2:a*2].decode('utf-16-le');script += [prefix,s['target']];reading += [prefix,s['reading'] or s['target']];end=b
  suffix=encoded[end*2:].decode('utf-16-le');script.append(suffix);reading.append(suffix)
  # Native projection may insert a documented separator for touching non-Roman slots.
  projection_equal=x['mixed_script']==''.join(script) and x['mixed_reading']==''.join(reading)
  covered={i for i,(a,b) in enumerate(words)if any(s['source_utf16'][0]<=a and b<=s['source_utf16'][1]for s in spans)}
  touched={i for i,(a,b) in enumerate(words)if any(s['source_utf16'][0]<b and a<s['source_utf16'][1]for s in spans)}
  evidence=x['source_evidence'];assert evidence['selected_route_only'];refs=evidence['references']
  for ref in refs:assert any(ref['scope']==s['source_utf16']for s in spans);assert len(ref['pack_sha'])==64
  for node in evidence['recognitions']:
   a,b=node['context'];assert 0<=a<b<=len(encoded)//2
   if node['mask'] is not None:ma,mb=node['mask'];assert a<=ma<mb<=b
  k='/'.join([x['stratum'],x['pair'],str(x['density'])]);g=groups.setdefault(k,{'messages':0,'nonempty':0,'source_native_words':0,'fully_covered_native_words':0,'touched_native_words':0,'spans':0,'multiword_focus_spans':0,'frame_spans':0,'starter_spans':0,'reference_hits':0,'no_selected_reference_spans':0,'projection_separator_differences':0,'statuses':collections.Counter(),'origins':collections.Counter(),'depths':[],'elapsed_ms':[],'reference_ids':set()})
  g['messages']+=1;g['nonempty']+=bool(spans);g['source_native_words']+=len(words);g['fully_covered_native_words']+=len(covered);g['touched_native_words']+=len(touched);g['spans']+=len(spans);g['reference_hits']+=x['reference_hit'];g['projection_separator_differences']+=not projection_equal
  g['statuses'][x['status']]+=1;g['origins'][str(x['origin'])]+=1;g['depths'].append(len(covered)/len(words)if words else 0);g['elapsed_ms'].append(x['elapsed_ms']);latency.append(x['elapsed_ms'])
  for s in spans:
   a,b=s['source_utf16'];g['multiword_focus_spans']+=sum(a<=wa and wb<=b for wa,wb in words)>=2
   ref=next((r for r in refs if r['scope']==[a,b]),None)
   if ref is None:g['no_selected_reference_spans']+=1
   elif ref['reference'].startswith('frame:'):g['frame_spans']+=1;g['reference_ids'].add(ref['reference'].split(':')[-1])
   else:g['starter_spans']+=1;g['reference_ids'].add(ref['reference'].split(':')[-1])
 assert seen==expected
 for g in groups.values():
  g['mean_raw_depth_including_zeros']=statistics.mean(g.pop('depths'));times=sorted(g.pop('elapsed_ms'));g['elapsed_ms']={'median':statistics.median(times),'p95':times[min(len(times)-1,int(.95*len(times)))],'max':max(times)};g['distinct_selected_reference_ids']=len(g['reference_ids']);g['reference_ids']=sorted(g['reference_ids'])
 receipt=json.loads((W/'android-capture-r01/receipt.json').read_text());assert receipt['success'] and receipt['closure']['main_unchanged'] and json.loads((W/'android-closure-reconciliation-r01.json').read_text())['capture_complete'] and json.loads((W/'android-closure-reconciliation-r01.json').read_text())['owned_process_absent']
 root=W/'android-capture-r01';assert (root/'settings-before.stdout').read_bytes()==(root/'settings-after.stdout').read_bytes()
 value={'rows':len(rows),'cases':len(cases),'groups':groups,'semantic_quality_assessed':False,'raw_availability_not_usefulness':True,'first_route_elapsed_ms':rows[0]['elapsed_ms'],'fresh_engine_each_row':True,'not_mobile_production_latency':True,'closure':receipt['closure'],'settings_unchanged':True,'bindings':{str(p):sha(p)for p in [inputs,raw,W/'selection-freeze.json',W/'protocol.json',root/'receipt.json',W/'android-closure-reconciliation-r01.json',Path(__file__)]}}
 out.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps({'bookkeeping_sha256':sha(out),'rows':len(rows),'cases':len(cases),'all_zero_translation_calls':True,'semantic_quality_assessed':False}))
if __name__=='__main__':main()
