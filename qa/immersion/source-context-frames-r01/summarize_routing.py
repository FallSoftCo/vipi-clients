#!/usr/bin/env python3
"""Read-only comparison of completed routing successor against both frozen original arms."""
from pathlib import Path
import json,hashlib,collections,math,argparse
W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def key(r):return r['pair'],r['id'],r['state'],r['density']
def sk(s):return tuple(s['source_utf16'])+(s['source'],s['target'],s.get('reading'))
def read(p):
 rows=[json.loads(x) for x in p.read_text().splitlines() if x.strip()];assert len(rows)==656;d={key(r):r for r in rows};assert len(d)==656;return d
def stats(xs):
 xs=sorted(xs);return {'count':len(xs),'min_ms':xs[0],'p50_ms':xs[math.ceil(len(xs)*.50)-1],'p95_ms':xs[math.ceil(len(xs)*.95)-1],'max_ms':xs[-1]}
def main():
 p=argparse.ArgumentParser();p.add_argument('--apple',type=Path,required=True);p.add_argument('--android',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();assert not a.out.exists()
 packet=json.loads((W/'review-merged-r01/anonymous-review.json').read_text());oldoptions={(c['pair'],c['source'],tuple(sk(s) for s in o['spans'])):o['option_id'] for c in packet['cases'] for o in c['options']}
 author={r['option_id']:r['label'] for r in json.loads((W/'author-review-r01.json').read_text())['judgments']};root={r['option_id']:r['label'] for r in json.loads((W/'root-review-r01.json').read_text())['labels']}
 metrics={};timings={};newoptions=[];deltas=[];branches={};newrows={};bindings=[];hashes={};parity={}
 for platform,newpath,oldpath in [('android',a.android,W/'android-capture-r01/output.stdout'),('apple',a.apple,W/'apple-run-r01/inputs-r02/frame-output.jsonl')]:
  old=read(oldpath);new=read(newpath);assert old.keys()==new.keys();newrows[platform]=new;hashes[platform]={'old':sha(oldpath),'new':sha(newpath)};bc=collections.Counter();checks=collections.Counter()
  for k,r in new.items():
   prior=old[k]
   for field in ['source','known_ids','native_words','baseline','candidate','starter_trace','frame_trace']:assert r[field]==prior[field],(platform,k,field)
   checks['direct_and_trace_rows']+=1;assert r['route']['baseline']==prior['route']['baseline'];checks['baseline_route_rows']+=1
   branch=r['routing_branch'];bc[branch]+=1
   if branch=='existing_forward_reference_baseline_evidence':assert r['route']['candidate']==r['route']['baseline'];checks['reference_restoration_rows']+=1
   elif branch=='reference_miss_frame_evidence':assert r['route']['candidate']==prior['route']['candidate'];checks['miss_original_candidate_rows']+=1
   else:raise AssertionError((platform,k,branch))
   t=r['timing'];assert t['fresh_engine_per_route']
   for field in ['direct_resolve_ms','baseline_setup_ms','candidate_setup_ms','baseline_result_ms','candidate_result_ms']:
    value=t[field];assert value>=0;timings.setdefault((platform,field,'all_fresh_engine' if 'result' in field else 'all'),[]).append(value)
   if t.get('reference_lookup_ms') is not None:timings.setdefault((platform,'reference_lookup_ms','first_pair_state' if t['first_reference_lookup_for_pair_state'] else 'later_shared_index'),[]).append(t['reference_lookup_ms'])
   for compare,base in [('vs_original_baseline',prior['route']['baseline']),('vs_original_candidate',prior['route']['candidate'])]:
    m=metrics.setdefault((platform,r['pair'],r['state'],r['density'],compare),collections.Counter());m['rows']+=1
    cand=r['route']['candidate'];sets={name:{sk(s) for s in value['spans']} for name,value in [('before',base),('after',cand)]}
    for name,value in [('before',base),('after',cand)]:
     m[name+'_nonempty']+=bool(value['spans']);m[name+'_units']+=len(value['spans']);m[name+'_native_words']+=sum(sum(start<=x and y<=end for x,y in r['native_words']) for s in value['spans'] for start,end in [s['source_utf16']])
    added=sets['after']-sets['before'];lost=sets['before']-sets['after'];m['added_units']+=len(added);m['lost_units']+=len(lost);m['empty_to_nonempty']+=not sets['before'] and bool(sets['after']);m['nonempty_to_empty']+=bool(sets['before']) and not sets['after'];m['changed_rows']+=bool(added or lost)
    if added or lost:deltas.append({'platform':platform,'key':k,'compare':compare,'source':r['source'],'before':base,'after':cand,'added':sorted(added,key=str),'lost':sorted(lost,key=str),'branch':branch})
   for arm in ['baseline','candidate']:
    result=r['route'][arm];oid=oldoptions.get((r['pair'],r['source'],tuple(sk(s) for s in result['spans'])))
    if oid is None:newoptions.append({'platform':platform,'key':k,'arm':arm,'source':r['source'],'output':result})
    else:bindings.append({'platform':platform,'key':k,'arm':arm,'option_id':oid,'author_label':author[oid],'root_label':root[oid]})
  branches[platform]=dict(bc);parity[platform]=dict(checks)
 differences=[]
 for k,r in newrows['android'].items():
  for arm in ['baseline','candidate']:
   x=r['route'][arm];y=newrows['apple'][k]['route'][arm]
   if x['spans']!=y['spans'] or x['mixed']!=y['mixed']:differences.append({'key':k,'arm':arm,'android':x,'apple':y})
 result={'input_sha256':hashes,'parity':parity,'branches':branches,'metrics':[dict(zip(['platform','pair','state','density','comparison'],k),**v) for k,v in sorted(metrics.items())],'timings':[dict(zip(['platform','measurement','regime'],k),**stats(v)) for k,v in sorted(timings.items())],'new_options':newoptions,'platform_differences':differences,'timing_limit':'Simulator/emulator fresh engine per row/arm, prior geometry/mechanism work and OS caches already exercised. First reference-index lookup separately reported. No production-device or total RSS claim.'}
 a.out.mkdir()
 for n,x in [('summary.json',result),('all-deltas.json',deltas),('frozen-label-bindings.json',bindings)]: (a.out/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
 (a.out/'receipt.json').write_text(json.dumps({'script_sha256':sha(Path(__file__)),'files':{n:sha(a.out/n) for n in ['summary.json','all-deltas.json','frozen-label-bindings.json']},'original_labels_unchanged':True},indent=2)+'\n');print(json.dumps({'parity':parity,'new_options':len(newoptions),'platform_differences':len(differences)}))
if __name__=='__main__':main()
