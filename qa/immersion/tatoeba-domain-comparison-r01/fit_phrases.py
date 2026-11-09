#!/usr/bin/env python3
"""Production-only adapter: one EN–ES fit and one frozen phrase arm.
Pure phrase functions are loaded unchanged from hash-bound AST nodes, never
from the old driver or by overriding its globals/paths.
"""
import argparse,ast,collections,gzip,hashlib,itertools,json,math,os,resource,shutil,signal,socket,sqlite3,subprocess,time,unicodedata
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=Path('/srv/fallsoft/staging/vipi-tatoeba-domain-comparison-20261108-r01')
ARM='grow-diag-final-and'

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def enc(x):return json.dumps(x,ensure_ascii=False,separators=(',',':'),sort_keys=True)
def write(path,obj):
 with path.open('x') as f:f.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def vm():return {k:int(v.split()[0])*1024 for k,v in (s.split(':',1) for s in Path('/proc/self/status').read_text().splitlines() if s.startswith(('VmHWM:','VmPeak:','VmRSS:')))}

def pure_functions(phrase_path,norm_path,bindings):
 env={'math':math,'unicodedata':unicodedata};node_hashes={}
 for path,names,constant in [(phrase_path,['crosses_stop','consistent_targets','parse_links','lexical_score'],'STOPS'),(norm_path,['norm'],None)]:
  assert sha(path)==bindings[path.name]
  source=path.read_text();tree=ast.parse(source);nodes=[]
  if constant:
   assign=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==constant for t in n.targets));env[constant]=ast.literal_eval(assign.value)
  for name in names:
   node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name);nodes.append(node);node_hashes[name]=hashlib.sha256(ast.get_source_segment(source,node).encode()).hexdigest()
  exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),env)
 return env,node_hashes

def command_plan():
 base=ROOT/'outputs/fetch/en-es.txt';out=ROOT/'outputs/fit-r01';tool=ROOT/'toolchain'
 return [{'name':'forward','argv':[str(tool/'fast_align'),'-i',str(base),'-d','-o','-v','-I','5','-p',str(out/'en-es-forward.params')],'stdout':'en-es-forward.align'},
 {'name':'reverse','argv':[str(tool/'fast_align'),'-i',str(base),'-d','-o','-v','-I','5','-p',str(out/'en-es-reverse.params'),'-r'],'stdout':'en-es-reverse.align'},
 {'name':ARM,'argv':[str(tool/'atools'),'-i',str(out/'en-es-forward.align'),'-j',str(out/'en-es-reverse.align'),'-c',ARM],'stdout':'en-es-'+ARM+'.align'}]

def main():
 parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['fit','phrases']);args=parser.parse_args()
 assert socket.gethostname()=='fallsoft-production-20261106';assert ROOT.resolve()==ROOT
 start=time.monotonic();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2)
 def timeout(*unused):raise TimeoutError('1200 second stage ceiling')
 signal.signal(signal.SIGALRM,timeout);signal.alarm(1200)
 assert shutil.disk_usage(ROOT).free>=8*1024**3+512*1024**2
 out=ROOT/'outputs'/('fit-r01' if args.stage=='fit' else 'phrases-r01');out.mkdir(exist_ok=False)
 receipt={'complete':False,'production':False,'stage':args.stage,'builder_sha256':sha(Path(__file__))};child=None;db=None
 def guard():
  assert time.monotonic()-start<1200
  assert shutil.disk_usage(ROOT).free>=8*1024**3
  assert sum(p.stat().st_size for p in (ROOT/'outputs').rglob('*') if p.is_file())<512*1024**2-65536
 try:
  plan=json.loads((HERE/'fit-plan-r01.json').read_text());assert sha(HERE/'protocol.json')==plan['protocol_sha256'];assert sha(Path(__file__))==plan['adapter_sha256']
  for rel,binding in plan['inputs'].items():
   path=ROOT/rel;assert path.resolve()==path and sha(path)==binding,rel
  assert plan['commands']==command_plan()
  receipt['plan_sha256']=sha(HERE/'fit-plan-r01.json')
  if args.stage=='fit':
   write(out/'execution-freeze.json',{'before_fit':True,'plan_sha256':receipt['plan_sha256'],'builder_sha256':receipt['builder_sha256'],'commands':plan['commands'],'bounds':plan['bounds'],'environment':{'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}})
   receipt['commands']=[]
   for command in plan['commands']:
    with (out/command['stdout']).open('xb') as output,(out/(command['name']+'.log')).open('xb') as log:
     child=subprocess.Popen(command['argv'],stdout=output,stderr=log,env=os.environ|{'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
     peak=0
     while child.poll() is None:
      stat=Path('/proc')/str(child.pid)/'status'
      try:peak=max(peak,int(next(s.split()[1] for s in stat.read_text().splitlines() if s.startswith('VmRSS:')))*1024)
      except (FileNotFoundError,StopIteration):pass
      guard();time.sleep(.2)
     assert child.returncode==0,(command['name'],child.returncode)
     receipt['commands'].append(command|{'exit_code':child.returncode,'child_peak_sampled_rss_bytes':peak});child=None
     write(out/(command['name']+'-complete.json'),receipt['commands'][-1])
   for filename in ['en-es-forward.align','en-es-reverse.align','en-es-'+ARM+'.align']:
    with (out/filename).open() as f:assert sum(1 for _ in f)==40000,filename
  else:
   fit=ROOT/'outputs/fit-r01';fitreceipt=json.loads((fit/'receipt.json').read_text());assert fitreceipt['complete'] and fitreceipt['plan_sha256']==receipt['plan_sha256']
   for name,binding in fitreceipt['outputs'].items():assert sha(fit/name)==binding['sha256']
   functions,function_hashes=pure_functions(ROOT/'adapter-deps/extract_phrases.py',ROOT/'adapter-deps/prepare_inputs.py',plan['pure_module_hashes'])
   norm,parse,score,consistent,cross=[functions[k] for k in ['norm','parse_links','lexical_score','consistent_targets','crosses_stop']]
   write(out/'execution-freeze.json',{'before_phrase_outputs':True,'plan_sha256':receipt['plan_sha256'],'builder_sha256':receipt['builder_sha256'],'fit_receipt_sha256':sha(fit/'receipt.json'),'pure_function_hashes':function_hashes,'pair':'en-es','arm':ARM,'source_max':8,'target_max':12,'no_driver_import_or_monkeypatch':True})
   frequency=json.loads((ROOT/'inputs/source-frequency-keys.json').read_text());keys={r['source_key'] for r in frequency['unigram_keys']+frequency['multiword_keys']};assert len(keys)==8000
   def params(path):
    result={}
    with path.open() as f:
     for i,line in enumerate(f):
      cond,pred,prob=line.rstrip('\n').split('\t');result[cond,pred]=float(prob)
      if i%20000==0:guard()
    return result
   forward=params(fit/'en-es-forward.params');reverse=params(fit/'en-es-reverse.params')
   db=sqlite3.connect(out/'candidates.sqlite');db.executescript('''PRAGMA temp_store=FILE; PRAGMA cache_size=-16384;
CREATE TABLE variants(id TEXT PRIMARY KEY,pair TEXT,arm TEXT,source_key TEXT,target_key TEXT,source_tokens INTEGER,target_tokens INTEGER,observations INTEGER,lexical_score_sum REAL,missing_lexical_parameters INTEGER,expanded_observations INTEGER,example_pair_index INTEGER,source_start INTEGER,source_end INTEGER,target_start INTEGER,target_end INTEGER) WITHOUT ROWID;
CREATE TABLE components(variant TEXT,component INTEGER,PRIMARY KEY(variant,component)) WITHOUT ROWID;
CREATE INDEX source_lookup ON variants(pair,arm,source_key);''')
   counts=collections.Counter();source_hits=collections.Counter()
   with gzip.open(ROOT/'outputs/fetch/en-es-pairs.jsonl.gz','rt') as pairs,(fit/('en-es-'+ARM+'.align')).open() as align,gzip.open(out/'en-es-observations.jsonl.gz','xt') as observations:
    for raw,alignment in itertools.zip_longest(pairs,align):
     assert raw is not None and alignment is not None
     row=json.loads(raw);assert row['index']==counts['sentence_pairs'] and row['pair']=='en-es';assert row['source']['component']==row['target']['component']
     st,tt=row['source']['tokens'],row['target']['tokens'];sw,tw=[t['text'].casefold() for t in st],[t['text'].casefold() for t in tt];links=parse(alignment,len(st),len(tt))
     for ss in range(len(st)):
      for se in range(ss+1,min(len(st),ss+8)+1):
       if cross(sw[ss:se]):break
       source_key=norm(row['source']['text'][st[ss]['codepoints'][0]:st[se-1]['codepoints'][1]])
       if source_key not in keys:continue
       source_hits[source_key]+=1;counts['source_inventory_occurrences']+=1
       for ts,te,lo,hi in consistent(ss,se,tw,links):
        target_key=norm(row['target']['text'][tt[ts]['codepoints'][0]:tt[te-1]['codepoints'][1]])
        identity=hashlib.sha256(json.dumps(['en-es',ARM,source_key,target_key],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        local={(s-ss,t-ts) for s,t in links if ss<=s<se and ts<=t<te};value,missing=score(sw[ss:se],tw[ts:te],local,forward,reverse);expanded=int((ts,te)!=(lo,hi))
        db.execute('''INSERT INTO variants VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET observations=observations+1,lexical_score_sum=lexical_score_sum+excluded.lexical_score_sum,missing_lexical_parameters=missing_lexical_parameters+excluded.missing_lexical_parameters,expanded_observations=expanded_observations+excluded.expanded_observations''',(identity,'en-es',ARM,source_key,target_key,se-ss,te-ts,1,value,missing,expanded,row['index'],ss,se,ts,te))
        db.execute('INSERT OR IGNORE INTO components VALUES(?,?)',(identity,row['source']['component']))
        observation={'variant_id':identity,'pair_index':row['index'],'pair_id':row['pair_id'],'component':row['source']['component'],'direct_edge':row['provenance']['direct_edge'],'arm':ARM,'source_tokens':[ss,se],'target_tokens':[ts,te],'minimal_target_tokens':[lo,hi],'source_codepoints':[st[ss]['codepoints'][0],st[se-1]['codepoints'][1]],'source_utf16':[st[ss]['utf16'][0],st[se-1]['utf16'][1]],'target_codepoints':[tt[ts]['codepoints'][0],tt[te-1]['codepoints'][1]],'target_utf16':[tt[ts]['utf16'][0],tt[te-1]['utf16'][1]],'links':sorted(local),'lexical_score':value,'missing_lexical_parameters':missing}
        observations.write(enc(observation)+'\n');counts['observations']+=1;counts['expanded_observations']+=expanded;counts['missing_lexical_parameters']+=missing
     counts['sentence_pairs']+=1
     if counts['sentence_pairs']%250==0:
      db.commit();guard()
      if counts['sentence_pairs']%2500==0:print(enc({'stage':'phrases','counts':dict(counts),'seconds':time.monotonic()-start}),flush=True)
   assert counts['sentence_pairs']==40000
   db.execute('''CREATE TABLE ranked AS SELECT v.*,count(c.component) AS distinct_components,v.lexical_score_sum/v.observations AS mean_lexical_score FROM variants v JOIN components c ON c.variant=v.id GROUP BY v.id''');db.execute('CREATE INDEX ranked_lookup ON ranked(pair,arm,source_key,distinct_components DESC,mean_lexical_score DESC,id)');db.commit()
   # No target spellings, IDs or scores in this first availability artifact.
   availability={key:{'variants':n,'observations':obs,'source_occurrences':source_hits[key],'maximum_variant_distinct_components':components} for key,n,obs,components in db.execute('SELECT source_key,count(*),sum(observations),max(distinct_components) FROM ranked GROUP BY source_key')}
   write(out/'source-availability.json',{'production':False,'source_only':True,'source_keys_sha256':plan['inputs']['inputs/source-frequency-keys.json'],'selected_key_denominator':8000,'keys':availability,'counts':dict(counts),'target_quality_claim':False})
   receipt['counts']=dict(counts);db.close();db=None
  guard();receipt['complete']=True
 except BaseException as exc:receipt['error']=repr(exc);raise
 finally:
  if child is not None and child.poll() is None:
   child.terminate()
   try:child.wait(timeout=5)
   except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
  if db is not None:db.close()
  receipt.update(seconds=time.monotonic()-start,measurement=vm(),outputs={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in out.iterdir() if p.is_file()})
  write(out/'receipt.json',receipt);print(enc(receipt),flush=True)
if __name__=='__main__':main()
