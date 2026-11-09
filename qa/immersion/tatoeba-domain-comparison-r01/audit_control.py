#!/usr/bin/env python3
"""One bounded aggregate-only audit of the unchanged local PGV control."""
import collections,gzip,hashlib,json,os,resource,signal,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
W=Path('/home/ai/Development/investigations/vipi-tatoeba-domain-comparison-20261108-r01')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 start=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(128*1024**2,)*2)
 def timeout(*args):raise TimeoutError('30-second audit ceiling')
 signal.signal(signal.SIGALRM,timeout);signal.alarm(30)
 out=W/'control-audit.json';assert not out.exists()
 receipt={'complete':False,'production':False,'script_sha256':sha(Path(__file__)),'scope':'Read unchanged local40kPGV manifest only; aggregate outputs, no text/targets/owners. No training.'}
 try:
  frozen=json.loads((W/'input-freeze.json').read_text());manifest=next(x for x in frozen['pgv_control'] if x['name']=='en-es-pairs.jsonl.gz');p=Path(manifest['path']);assert sha(p)==manifest['sha256']
  exclusion=json.loads((W/'exclusions.json').read_text());assert sha(W/'exclusions.json')==frozen['exclusions']['sha256'];expanded=set(exclusion['hashes'])
  basepath=Path(exclusion['inputs'][0]['path']);assert sha(basepath)==exclusion['inputs'][0]['sha256'];base=set(json.loads(basepath.read_text())['hashes']);added=expanded-base
  counts=collections.Counter();lengths={k:collections.Counter() for k in ['en','es']};components=collections.Counter();owners={k:collections.Counter() for k in ['en','es']};fingerprints={k:set() for k in ['en','es']}
  with gzip.open(p,'rt') as f:
   for line in f:
    row=json.loads(line);assert row['pair']=='en-es';counts['pairs']+=1
    endpoints=[row['source'],row['target']];assert all(e['partition']=='development' for e in endpoints)
    for name,values in [('original1113',base),('expanded',expanded),('subsequent_only',added)]:
     counts[name+'_pairs_overlap']+=any(e['fingerprint'] in values for e in endpoints)
     for e in endpoints:counts[name+'_'+e['language']+'_endpoint_occurrences']+=e['fingerprint'] in values
    components[(endpoints[0]['component'],endpoints[1]['component'])]+=1
    for e in endpoints:
     lang=e['language'];lengths[lang][len(e['tokens'])]+=1;owners[lang][e['owner']]+=1;fingerprints[lang].add(e['fingerprint'])
  assert counts['pairs']==40000
  receipt.update(complete=True,manifest_sha256=manifest['sha256'],exclusions_sha256=frozen['exclusions']['sha256'],counts=dict(counts),distinct_component_pairs=len(components),largest_component_pair_count=max(components.values()),endpoint_aggregates={lang:{'distinct_owners':len(owners[lang]),'largest_owner_pair_count':max(owners[lang].values()),'blank_owner_pair_count':owners[lang].get('',0),'distinct_fulltext_fingerprints':len(fingerprints[lang]),'token_histogram':dict(lengths[lang]),'total_tokens':sum(k*v for k,v in lengths[lang].items())} for lang in ['en','es']},limits={'cpu':1,'address_space_bytes':128*1024**2,'seconds':30,'output_bytes':1024**2})
 except BaseException as exc:receipt['error']=repr(exc);raise
 finally:
  receipt.update(seconds=time.monotonic()-start,VmHWM_bytes=int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmHWM:')))*1024)
  text=json.dumps(receipt,indent=2)+'\n';assert len(text.encode())<1024**2
  with out.open('x') as f:f.write(text)
  print(text)
if __name__=='__main__':main()
