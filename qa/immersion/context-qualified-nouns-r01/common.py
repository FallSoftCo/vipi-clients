"""Frozen context gate primitives; baseline records and source masks are immutable."""
import ast,collections,gzip,hashlib,importlib.util,json,math,os,pathlib,re,resource,shutil,signal,socket,time,unicodedata
R=pathlib.Path('/srv/fallsoft/staging/vipi-context-qualified-nouns-20261109-r01');M=1024**2;KNOWN=['all_function','all_function_global300']
def enc(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(enc(x).encode()).hexdigest()
def sha(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def norm(x):return ' '.join(unicodedata.normalize('NFC',x).casefold().split())
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def tokenizer(path):
 tree=ast.parse(pathlib.Path(path).read_text());nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='tokenize' or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='TOKEN' for t in n.targets)];env={'re':re};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),env);return env['tokenize']
def windows(key,values,focus):
 out=[]
 for n in range(2,9):
  for a in range(focus-n+1,focus+1):
   b=a+n
   if a<0 or b>len(values) or any(not any(c.isalpha() for c in v) for v in values[a:b]):continue
   out.append((enc([key,focus-a,values[a:b]]),a,b))
 return out

def rank_rule(x):
 r=x['rule'];return (-r['length'],-(r['ratio'] if r['ratio'] is not None else math.inf),-r['winner_components'],-r['winner_weight'],x['tokens'][0],r['id'])
def controls(tok):
 assert not windows('x',[norm(x[0]) for x in tok('red, dog')],2)
 assert not windows('x',[norm(x[0]) for x in tok('red. dog')],2)
 assert len(windows('x',[norm(x[0]) for x in tok("my dog's bed")],1))==3
 assert windows('x',['title'],0)==[]
 assert rank_rule({'rule':{'length':4,'ratio':2,'winner_components':2,'winner_weight':1,'id':'a'},'tokens':[0,4]})<rank_rule({'rule':{'length':3,'ratio':9,'winner_components':8,'winner_weight':8,'id':'b'},'tokens':[0,3]})
 return True

class Run:
 def __init__(self,stage):
  assert socket.gethostname()=='fallsoft-production-20261106';self.start=time.monotonic();self.p=json.loads((R/'protocol.json').read_text());self.paths={k:pathlib.Path(v['path']) for k,v in self.p['inputs'].items()};self.out=R/stage;self.out.mkdir(exist_ok=False);self.r={'complete':False,'stage':stage,'protocol_sha256':sha(R/'protocol.json')};os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2);signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('frozen bound')));signal.alarm(self.p['seconds'][stage]);self.r['free_bytes']=shutil.disk_usage(R).free;assert self.r['free_bytes']>8*1024**3+192*M
 def verify(self):
  for n,h in self.p['code_hashes'].items():assert sha(R/n)==h,n
  for k,v in self.p['inputs'].items():assert sha(v['path'])==v['sha256'],k
  self.tokenize=tokenizer(self.paths['tokenizer']);assert controls(self.tokenize)
 def write(self,name,v):
  b=(enc(v)+'\n').encode();assert len(b)+sum(p.stat().st_size for p in R.rglob('*') if p.is_file())<128*M;(self.out/name).write_bytes(b)
 def prior(self,name):
  r=json.loads((R/name/'receipt.json').read_text());assert r['complete'] and r['protocol_sha256']==sha(R/'protocol.json')
  for n,v in r['outputs'].items():assert sha(R/name/n)==v['sha256']
  return R/name
 def finish(self,error=None):
  self.r.update(complete=error is None,error=error,seconds=time.monotonic()-self.start,VmHWM_bytes=int(next(s.split()[1] for s in pathlib.Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:')))*1024,outputs={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in self.out.iterdir() if p.is_file()});self.write('receipt.json',self.r);print(enc(self.r),flush=True)

def translated(selector,trace,indices,known,order):
 c=trace['candidates'];s=selector.select([c[i] for i in indices],trace['native_words_utf16'],trace['protected_ranges_utf16'],trace['source_masks'],.25,known,order);v={k:[indices[i] for i in s[k]] for k in ['selected_indices','pre_budget_indices','budget_only_indices']};v.update(budget=s['budget'],rejected=[dict(x,index=indices[x['index']]) for x in s['rejected']]);raw=trace['text'].encode('utf-16-le')
 for i in v['selected_indices']:
  a,b=c[i]['focus_utf16'];assert c[i]['cost']==sum(a<=x and y<=b for x,y in trace['native_words_utf16']),('depth',trace.get('id'),i)
 for i in sorted(v['selected_indices'],key=lambda i:c[i]['focus_utf16'][0],reverse=True):
  a,b=c[i]['focus_utf16'];raw=raw[:2*a]+c[i]['target'].encode('utf-16-le')+raw[2*b:]
 v['mixed_output']=raw.decode('utf-16-le');return json.loads(enc(v))
