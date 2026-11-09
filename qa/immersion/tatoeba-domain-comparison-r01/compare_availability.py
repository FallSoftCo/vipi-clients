#!/usr/bin/env python3
"""Small local read-only control summary and source-only frozen review-key selection."""
import collections,hashlib,json,os,resource,shutil,signal,sqlite3,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
W=Path('/home/ai/Development/investigations/vipi-tatoeba-domain-comparison-20261108-r01')
PGV=Path('/home/ai/Development/investigations/vipi-immersion-reconciliation-20261107-r01/corpus-phrase-extraction-r01')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def write(p,obj):
 with p.open('x') as f:f.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def main():
 start=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(128*1024**2,)*2)
 def timeout(*args):raise TimeoutError('60 second source-only comparison limit')
 signal.signal(signal.SIGALRM,timeout);signal.alarm(60)
 assert shutil.disk_usage(W).free>=8*1024**3+16*1024**2
 out=W/'source-comparison-r01';out.mkdir(exist_ok=False)
 receipt={'complete':False,'production':False,'code_sha256':sha(Path(__file__))};db=None
 try:
  protocol=json.loads((HERE/'protocol.json').read_text());assert sha(HERE/'protocol.json')=='7aab49bf0aa81e478922feb9e655d2369bacdbf97bd98f76b93f3a5fcc9e5d65'
  # Only these small successful production outputs may be copied locally.
  remote=W/'fit-evidence-r01';phrase_receipt=json.loads((remote/'phrases-receipt.json').read_text());assert phrase_receipt['complete']
  availability=remote/'source-availability.json';assert sha(availability)==phrase_receipt['outputs']['source-availability.json']['sha256'];t=json.loads(availability.read_text())['keys']
  keys_path=PGV/'source-frequency-keys.json';assert sha(keys_path)==protocol['matched_recipe']['source_keys']['sha256'];freq=json.loads(keys_path.read_text());keys={r['source_key']:r for r in freq['unigram_keys']+freq['multiword_keys']};assert len(keys)==8000 and set(t)<=set(keys)
  control=PGV/'phrases/candidates.sqlite';oldreceipt=json.loads((PGV/'phrases/receipt.json').read_text());assert sha(control)==oldreceipt['outputs']['candidates.sqlite']['sha256']
  db=sqlite3.connect(control.as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA cache_size=-8192');db.execute('PRAGMA query_only=ON');db.set_progress_handler(lambda:int(time.monotonic()-start>60),10000)
  p={k:{'variants':n,'observations':o,'maximum_variant_distinct_components':c} for k,n,o,c in db.execute("SELECT source_key,count(*),sum(observations),max(distinct_components) FROM ranked WHERE pair='en-es' AND arm='grow-diag-final-and' GROUP BY source_key")};assert set(p)<=set(keys)
  def length(k):
   costs=keys[k]['observed_native_costs'];assert len(costs)==1
   n=costs[0];return '1' if n==1 else '2-3' if n<=3 else '4-8'
  buckets={'shared':set(t)&set(p),'tatoeba_only':set(t)-set(p),'pgv_only':set(p)-set(t)}
  stats={bucket:{size:sum(length(k)==size for k in values) for size in ['1','2-3','4-8']} for bucket,values in buckets.items()}
  sampling=protocol['matched_recipe']['semantic_packet'];selected=[];shortages=[]
  for bucket in sampling['source_key_buckets_order']:
   for size,quota in zip(sampling['length_buckets_order'],sampling['keys_per_availability_length']):
    ranked=sorted((hashlib.sha256('|'.join([sampling['seed'],bucket,size,k]).encode()).hexdigest(),k) for k in buckets[bucket] if length(k)==size)
    chosen=ranked[:quota]
    if len(chosen)<quota:shortages.append({'bucket':bucket,'length':size,'quota':quota,'actual':len(chosen)})
    for rank,k in chosen:selected.append({'source_key':k,'bucket':bucket,'length':size,'sampling_hash':rank,'corpora':['tatoeba','pgv'] if bucket=='shared' else ['tatoeba'] if bucket=='tatoeba_only' else ['pgv']})
  assert sum(len(r['corpora']) for r in selected)<=32
  bindings={'protocol_sha256':sha(HERE/'protocol.json'),'tatoeba_phrase_receipt_sha256':sha(remote/'phrases-receipt.json'),'tatoeba_source_availability_sha256':sha(availability),'pgv_candidates_sha256':sha(control),'source_keys_sha256':sha(keys_path)}
  write(out/'review-key-freeze.json',{'production':False,'before_target_packet_or_target_quality_inspection':True,'bindings':bindings,'policy':sampling,'length_definition':'Frozen source-key observed_native_costs, unique cost (mixed-cost keys were previously withheld).','selected':selected,'proposal_count':sum(len(r['corpora']) for r in selected),'shortages':shortages})
  write(out/'source-inventory.json',{'production':False,'source_only':True,'selected_source_key_denominator':8000,'bindings':bindings,'availability_by_length':stats,'neither_available':8000-len(set(t)|set(p)),'tatoeba':t,'pgv':p,'interpretation':'Availability/observations/component support only; no semantic quality, construction completeness or conversational coverage claim.'})
  receipt.update(complete=True,bindings=bindings,availability_by_length=stats,tatoeba_keys=len(t),pgv_keys=len(p),neither_available=8000-len(set(t)|set(p)),review_proposals=sum(len(r['corpora']) for r in selected))
 except BaseException as exc:receipt['error']=repr(exc);raise
 finally:
  if db:db.close()
  receipt.update(seconds=time.monotonic()-start,VmHWM_bytes=int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmHWM:')))*1024,outputs={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()})
  write(out/'receipt.json',receipt);print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
