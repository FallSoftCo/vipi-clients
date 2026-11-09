import collections,gzip,hashlib,json,os,resource,shutil,signal,socket,time
from pathlib import Path
R=Path('/srv/fallsoft/staging/vipi-apertium-corpus-evidence-20261109-r01');L=Path('/srv/fallsoft/staging/vipi-lexical-choice-evidence-20261109-r01')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def main():
 assert socket.gethostname()=='fallsoft-production-20261106';assert shutil.disk_usage(R).free>8*1024**3+8*1024**2;os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.alarm(120);start=time.monotonic();out=R/'cohort';out.mkdir(exist_ok=False);receipt={'complete':False}
 try:
  protocol=json.loads((L/'code/protocol-r02.json').read_text());paths={k:Path(protocol['inputs'][k]['path']) for k in ('observations','pairs')}
  for k,p in paths.items():assert sha(p)==protocol['inputs'][k]['sha256']
  scope=L/'outputs/metadata/scope-freeze.json';vc=L/'outputs/metadata/variant-census.json';s=json.loads(scope.read_text());v=json.loads(vc.read_text());assert len(s['new_head_ids'])==1480;bykey=collections.defaultdict(list)
  for h in s['new_head_ids']:bykey[h['source_key']].append(h)
  variants={x['id']:dict(x,source_key=k) for k,c in v.items() for x in c['variants']};seen=collections.Counter();pairs={};headjoins=0;focuses=collections.defaultdict(list)
  with gzip.open(paths['observations'],'rt') as f:
   for line in f:
    o=json.loads(line)
    if o['variant_id'] not in variants:continue
    seen[o['variant_id']]+=1;key=variants[o['variant_id']]['source_key'];assert o['pair_index'] not in pairs or pairs[o['pair_index']]==(o['pair_id'],o['component']);pairs[o['pair_index']]=(o['pair_id'],o['component'])
    for h in bykey[key]:
     a,b=[o['source_tokens'][0]+x for x in h['relative_focus_tokens']];focuses[o['pair_index']].append((h['id'],a,b));headjoins+=1
  assert sum(seen.values())==12485 and headjoins==12500
  assert all(seen[i]==x['observations'] for i,x in variants.items())
  endpoints={};components=set();sourcefocus=set();count=0;token_totals=collections.Counter();textbytes=collections.Counter()
  with gzip.open(paths['pairs'],'rt') as f:
   for line in f:
    p=json.loads(line)
    if p['index'] not in pairs:continue
    count+=1;assert pairs[p['index']]==(p['pair_id'],p['source']['component']);assert p['source']['component']==p['target']['component'];components.add(p['source']['component'])
    for h,a,b in focuses[p['index']]:assert 0<=a<b<=len(p['source']['tokens']);sourcefocus.add((p['source']['id'],p['source']['fingerprint'],p['source']['record_sha256'],a,b))
    for side in ('source','target'):
     e=p[side];identity=[e['language'],e['id'],e['text'],e['tokens']];key=hashlib.sha256(json.dumps(identity,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
     if key not in endpoints:
      endpoints[key]={'language':e['language'],'endpoint_id':e['id'],'fingerprint':e['fingerprint'],'record_sha256':e['record_sha256'],'text_sha256':hashlib.sha256(e['text'].encode()).hexdigest(),'token_geometry_sha256':hashlib.sha256(json.dumps(e['tokens'],sort_keys=True).encode()).hexdigest(),'tokens':len(e['tokens']),'utf8_bytes':len(e['text'].encode()),'pair_ids':[]};token_totals[e['language']]+=len(e['tokens']);textbytes[e['language']]+=len(e['text'].encode())
     endpoints[key]['pair_ids'].append(p['pair_id'])
  assert count==len(pairs)
  result={'inputs':{str(p):sha(p) for p in [scope,vc,*paths.values()]},'heads':1480,'source_keys':len(v),'variants':len(variants),'observations':sum(seen.values()),'head_observation_joins':headjoins,'distinct_pairs':count,'distinct_components':len(components),'distinct_source_focus_occurrences':len(sourcefocus),'distinct_endpoints':len(endpoints),'endpoints_by_language':dict(collections.Counter(x['language'] for x in endpoints.values())),'tokens_by_language':dict(token_totals),'utf8_text_bytes_by_language':dict(textbytes),'endpoints':endpoints,'no_annotation':True}
  b=(json.dumps(result,ensure_ascii=False,sort_keys=True)+'\n').encode();assert len(b)<8*1024**2;(out/'endpoint-inventory.json').write_bytes(b);receipt.update(complete=True,output_sha256=sha(out/'endpoint-inventory.json'),output_bytes=len(b),summary={k:v for k,v in result.items() if k not in ('inputs','endpoints')})
 except BaseException as e:receipt['error']=repr(e);raise
 finally:
  receipt.update(seconds=time.monotonic()-start,VmHWM_bytes=int(next(s.split()[1] for s in Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:')))*1024,script_sha256=sha(Path(__file__)));(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
if __name__=='__main__':main()
