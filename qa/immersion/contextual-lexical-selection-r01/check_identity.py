import collections,gzip,hashlib,json,os,resource,signal,time,unicodedata
from pathlib import Path
R=Path('/srv/fallsoft/staging/vipi-contextual-lexical-selection-20261109-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def norm(t):return ' '.join(unicodedata.normalize('NFC',t).casefold().split())
def main():
 start=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.alarm(120);out=R/'identity-preflight.json';assert not out.exists();plan=json.loads((R/'protocol.json').read_text());receipt=json.loads((R/'prepare/receipt.json').read_text());assert receipt['complete'];split=json.loads((R/'prepare/split-freeze.json').read_text());data=json.loads((R/'prepare/dataset.json').read_text());assert sha(R/'prepare/dataset.json')==receipt['outputs']['dataset.json']['sha256'];assert sha(R/'prepare/split-freeze.json')==receipt['outputs']['split-freeze.json']['sha256'];exposed=set(split['exposed_components']);groups=collections.defaultdict(lambda:collections.defaultdict(set));eligible=collections.defaultdict(lambda:collections.defaultdict(set))
 def part(c):return 'development' if c in exposed else 'test' if int(hashlib.sha256(enc(['contextual-lexical-selection-r01',c]).encode()).hexdigest()[:16],16)%5==0 else 'train'
 with gzip.open(plan['inputs']['pairs']['path'],'rt') as f:
  for line in f:
   e=json.loads(line)['source'];h=hashlib.sha256(norm(e['text']).encode()).hexdigest();groups[h][part(e['component'])].add(e['component'])
 for row in data['rows']:
  e=data['endpoints'][row['endpoint']];assert part(e['component'])==row['split'];h=hashlib.sha256(norm(e['text']).encode()).hexdigest();eligible[h][row['split']].add(row['component'])
 def overlaps(g):return {h:{k:sorted(v) for k,v in m.items()} for h,m in sorted(g.items()) if len(m)>1}
 a,b=overlaps(groups),overlaps(eligible);value={'complete':True,'prediction_allowed':not a and not b,'all40k_normalized_source_text_overlap':a,'eligible_normalized_source_text_overlap':b,'all40k_unique_normalized_sources':len(groups),'eligible_unique_normalized_sources':len(eligible),'protocol_sha256':sha(R/'protocol.json'),'split_sha256':sha(R/'prepare/split-freeze.json'),'code_sha256':sha(Path(__file__)),'seconds':time.monotonic()-start,'VmHWM_bytes':int(next(s.split()[1] for s in Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:')))*1024};out.write_text(json.dumps(value,indent=2)+'\n');print(enc({k:v for k,v in value.items() if 'overlap' not in k}));print('overlap_counts',len(a),len(b))
if __name__=='__main__':main()
