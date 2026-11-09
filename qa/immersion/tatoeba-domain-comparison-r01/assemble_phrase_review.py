#!/usr/bin/env python3
"""Keyed top-variant evidence after source-key freeze, then one private packet.
No fit, selection-policy change or semantic labels. Full variants remain in DB.
"""
import argparse,gzip,hashlib,json,os,resource,shutil,signal,socket,sqlite3,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
LOCAL=Path('/home/ai/Development/investigations/vipi-tatoeba-domain-comparison-20261108-r01')
PGV=Path('/home/ai/Development/investigations/vipi-immersion-reconciliation-20261107-r01/corpus-phrase-extraction-r01')
REMOTE=Path('/srv/fallsoft/staging/vipi-tatoeba-domain-comparison-20261108-r01')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def write(p,value):
 with p.open('x') as f:f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def main():
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['tatoeba','pgv','join']);p.add_argument('--selection-sha256',required=True);a=p.parse_args()
 start=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2)
 def timeout(*unused):raise TimeoutError('120-second evidence assembly ceiling')
 signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
 if a.stage=='tatoeba':
  assert socket.gethostname()=='fallsoft-production-20261106';assert REMOTE.resolve()==REMOTE
  selection=REMOTE/'inputs/review-key-freeze.json';work=REMOTE/'outputs/review-evidence-r01'
 else:selection=LOCAL/'source-comparison-r01/review-key-freeze.json';work=LOCAL/'review-evidence-r01'
 assert sha(selection)==a.selection_sha256
 assert shutil.disk_usage(work.parent).free>=8*1024**3+16*1024**2
 work.mkdir(exist_ok=True);receipt_path=work/(a.stage+'-receipt.json');assert not receipt_path.exists();receipt={'complete':False,'production':False,'stage':a.stage,'selection_sha256':a.selection_sha256,'script_sha256':sha(Path(__file__))};db=None
 try:
  frozen=json.loads(selection.read_text());assert frozen['before_target_packet_or_target_quality_inspection']
  if a.stage=='join':
   all_rows={};bindings={}
   for corpus in ['tatoeba','pgv']:
    f=work/(corpus+'-evidence.json');r=json.loads((work/(corpus+'-receipt.json')).read_text());assert r['complete'] and r['selection_sha256']==a.selection_sha256;assert sha(f)==r['outputs'][f.name]['sha256'];bindings[corpus]=sha(f)
    all_rows[corpus]={c['source_key']:c for c in json.loads(f.read_text())['cases']}
   cases=[]
   for selected in frozen['selected']:
    for corpus in selected['corpora']:
     c=all_rows[corpus][selected['source_key']];cases.append({'review_id':'domain-'+str(len(cases)+1).zfill(3),'corpus':corpus,'selection':selected,**c})
   assert len(cases)==frozen['proposal_count']<=32
   write(work/'review-packet.json',{'schema':1,'production':False,'semantic_labels_present':False,'selection_sha256':a.selection_sha256,'evidence_hashes':bindings,'cases':cases,'limits':'Reused diagnostic source keys; complete parallel-sentence evidence, no native mixed-output projection. Review entire emitted phrase and source sense/form, not only a head. Consistency is not completeness.'});receipt['proposal_count']=len(cases)
  else:
   corpus=a.stage
   if corpus=='tatoeba':
    phrases=REMOTE/'outputs/phrases-r01';pairs=REMOTE/'outputs/fetch/en-es-pairs.jsonl.gz';obs=phrases/'en-es-observations.jsonl.gz';r=json.loads((phrases/'receipt.json').read_text());assert r['complete']
    assert sha(phrases/'receipt.json')==frozen['bindings']['tatoeba_phrase_receipt_sha256'];assert sha(pairs)=='4eabc120af4d8cf31a8ba85709d7e9408cc06623fa585b0f3355e915eb6b8268'
   else:
    phrases=PGV/'phrases';pairs=PGV/'en-es-pairs.jsonl.gz';obs=phrases/'en-es-observations.jsonl.gz';r=json.loads((phrases/'receipt.json').read_text());assert r['complete'];assert sha(pairs)=='2968021613e98886ecacb02d34503535d70743fc50805dca7baa6115cc00eae4'
   for name in ['candidates.sqlite','en-es-observations.jsonl.gz']:assert sha(phrases/name)==r['outputs'][name]['sha256']
   db=sqlite3.connect((phrases/'candidates.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-8192');db.row_factory=sqlite3.Row
   variants={};top={}
   for s in frozen['selected']:
    if corpus not in s['corpora']:continue
    rows=[dict(row) for row in db.execute("SELECT * FROM ranked WHERE pair='en-es' AND arm='grow-diag-final-and' AND source_key=? ORDER BY distinct_components DESC,mean_lexical_score DESC,id",(s['source_key'],))];assert rows
    variants[s['source_key']]=rows;top[rows[0]['id']]=s['source_key']
   # Retain only pair metadata in memory while scanning observations.
   meta={}
   with gzip.open(pairs,'rt') as f:
    for line in f:
     row=json.loads(line);assert row['source']['component']==row['target']['component'];meta[row['index']]=(row['source']['component'],row['pair_id'])
   assert len(meta)==40000
   best={};observed={v:0 for v in top}
   with gzip.open(obs,'rt') as f:
    for line in f:
     o=json.loads(line);v=o['variant_id']
     if v not in top:continue
     rank=meta[o['pair_index']]+tuple(o['source_tokens'])+tuple(o['target_tokens']);observed[v]+=1
     if v not in best or rank<best[v][0]:best[v]=(rank,o)
   assert set(best)==set(top)
   retained={};needed={o['pair_index'] for _,o in best.values()}
   with gzip.open(pairs,'rt') as f:
    for line in f:
     row=json.loads(line)
     if row['index'] in needed:retained[row['index']]=row
   cases=[]
   for key,alternatives in variants.items():
    chosen=alternatives[0];rank,o=best[chosen['id']];row=retained[o['pair_index']];assert observed[chosen['id']]==chosen['observations']
    ss,se=o['source_codepoints'];ts,te=o['target_codepoints'];source=row['source']['text'];target=row['target']['text'];emitted=target[ts:te]
    assert row['source']['text'].encode('utf-16-le')[2*o['source_utf16'][0]:2*o['source_utf16'][1]].decode('utf-16-le')==source[ss:se]
    assert row['target']['text'].encode('utf-16-le')[2*o['target_utf16'][0]:2*o['target_utf16'][1]].decode('utf-16-le')==emitted
    cases.append({'source_key':key,'chosen_variant':chosen,'all_ranked_variants':alternatives,'observation':o,'evidence_rank':list(rank),'full_parallel_record':row,'source_phrase':source[ss:se],'target_phrase':emitted,'single_phrase_mixed_output':source[:ss]+emitted+source[se:],'emitted_units':[{'source_codepoints':[ss,se],'source_utf16':o['source_utf16'],'target_codepoints':[ts,te],'target_utf16':o['target_utf16'],'target':emitted}],'review_scope':'Full parallel source/target sentences and entire emitted phrase; not a budgeted runtime output or target-quality approval.'})
   write(work/(corpus+'-evidence.json'),{'production':False,'semantic_labels_present':False,'selection_sha256':a.selection_sha256,'cases':cases});receipt.update(proposals=len(cases),source_bindings={'pairs_sha256':sha(pairs),'observations_sha256':sha(obs),'candidates_sha256':sha(phrases/'candidates.sqlite')})
  assert sum(p.stat().st_size for p in work.iterdir() if p.is_file())<16*1024**2-65536;receipt['complete']=True
 except BaseException as exc:receipt['error']=repr(exc);raise
 finally:
  if db:db.close()
  receipt.update(seconds=time.monotonic()-start,VmHWM_bytes=int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmHWM:')))*1024,outputs={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in work.iterdir() if p.is_file() and p.name.endswith('.json') and not p.name.endswith('-receipt.json')})
  write(receipt_path,receipt);print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
