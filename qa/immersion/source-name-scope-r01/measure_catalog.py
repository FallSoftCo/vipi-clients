#!/usr/bin/env python3
"""Read-only exact catalog payload measurement; replacement DB creation prohibited."""
import ast,collections,contextlib,hashlib,importlib.util,json,os,resource,shutil,signal,socket,sqlite3,sys,time
from pathlib import Path
ROOT=Path('/srv/fallsoft/staging/vipi-source-name-scope-20261109-r01')
HERE=ROOT/'code'
LIMIT=2*1024**2
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def write(out,name,x):
 b=(json.dumps(x,sort_keys=True,indent=2)+'\n').encode();assert sum(p.stat().st_size for p in out.iterdir() if p.is_file())+len(b)<LIMIT
 with (out/name).open('xb') as f:f.write(b)
class Counter:
 def __init__(self):self.ids=set();self.rows=0;self.columns=collections.Counter();self.sizes=[];self.hist=collections.Counter();self.baseline=0;self.experimental=0
 def execute(self,sql,args=()):
  if sql.startswith('PRAGMA '):
   assert sql in ['PRAGMA cache_size=-8192','PRAGMA max_page_count=4096'];return
  assert sql=='INSERT INTO heads VALUES(?,?,?,?,?,?)' and len(args)==6
  assert args[0] not in self.ids;self.ids.add(args[0]);assert args[2] in [0,1] and args[3] in [0,1]
  sizes={k:len(v.encode('utf-8')) for k,v in zip(['id','source_key','record','audit'],[args[0],args[1],args[4],args[5]])}
  n=sum(sizes.values());self.columns.update(sizes);self.rows+=1;self.sizes.append(n);self.hist[str(1<<(max(1,n)-1).bit_length())]+=1;self.baseline+=args[2];self.experimental+=args[3]
 def executescript(self,sql):assert sql=='CREATE TABLE heads(id TEXT PRIMARY KEY,source_key TEXT,baseline INTEGER,experimental INTEGER,record TEXT,audit TEXT) WITHOUT ROWID; CREATE INDEX lookup ON heads(source_key);'
 def commit(self):pass
 def close(self):pass
 def result(self):
  s=sorted(self.sizes)
  return {'rows':self.rows,'baseline_rows':self.baseline,'experimental_rows':self.experimental,'utf8_column_bytes':dict(self.columns),'utf8_payload_bytes':sum(self.columns.values()),'integer_flag_values':2*self.rows,'row_utf8_max':max(s),'row_utf8_quantiles':{str(p):s[((len(s)-1)*p)//100] for p in [0,25,50,75,90,95,99,100]},'row_utf8_histogram_upper_bound':dict(sorted(self.hist.items(),key=lambda x:int(x[0]))),'sqlite_serial_headers_cell_pointers_page_slack_and_secondary_index_not_in_utf8_payload':True}
def main():
 assert socket.gethostname()=='fallsoft-production-20261106' and Path(__file__).resolve()==HERE/'measure_catalog.py'
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1024**3,)*2)
 def timeout(*args):raise TimeoutError('120s measurement ceiling')
 signal.signal(signal.SIGALRM,timeout);signal.alarm(120);assert shutil.disk_usage(ROOT).free>=8*1024**3+LIMIT
 out=ROOT/'outputs/catalog-size-measurement-r01';out.mkdir(exist_ok=False);start=time.monotonic();receipt={'complete':False,'script_sha256':sha(__file__)};stack=contextlib.ExitStack()
 try:
  expected=json.loads((HERE/'measurement-plan.json').read_text());assert expected['script_sha256']==receipt['script_sha256'];receipt['plan_sha256']=sha(HERE/'measurement-plan.json')
  plan=json.loads((HERE/'protocol.json').read_text());assert sha(HERE/'protocol.json')==expected['parent_protocol_sha256']
  for name,digest in plan['code_hashes'].items():assert sha(HERE/name)==digest
  for name,b in plan['inputs'].items():assert sha(Path(b['path']))==b['sha256']
  partial=ROOT/'outputs/catalog/catalog.sqlite';assert sha(partial)==expected['partial_sha256']
  failure=ROOT/'outputs/catalog/receipt.json';assert sha(failure)==expected['failure_receipt_sha256']
  receipt.update(input_bindings=plan['inputs'],parent_code_hashes=plan['code_hashes'],partial_sha256=sha(partial),failure_receipt_sha256=sha(failure))
  db=sqlite3.connect(partial.as_uri()+'?mode=ro&immutable=1',uri=True);stack.callback(db.close);db.execute('PRAGMA cache_size=-8192')
  pages={key:db.execute('PRAGMA '+key).fetchone()[0] for key in ['page_count','page_size','freelist_count']}
  fields=['id','source_key','record','audit'];sums=db.execute('SELECT count(*),'+','.join('sum(length(CAST('+k+' AS BLOB)))' for k in fields)+',max('+ '+'.join('length(CAST('+k+' AS BLOB))' for k in fields)+') FROM heads').fetchone()
  prefix={'file_bytes':partial.stat().st_size,**pages,'rows':sums[0],'utf8_column_bytes':dict(zip(fields,sums[1:5])),'utf8_payload_bytes':sum(sums[1:5]),'max_row_utf8':sums[5],'distinct_contexts':db.execute("SELECT count(DISTINCT json_extract(audit,'$.context_id')) FROM heads").fetchone()[0]}
  try:prefix['dbstat']=[dict(zip(['object','pages','page_bytes','payload','unused','max_payload'],row)) for row in db.execute('SELECT name,count(*),sum(pgsize),sum(payload),sum(unused),max(mx_payload) FROM dbstat GROUP BY name ORDER BY name')]
  except sqlite3.OperationalError as e:prefix['dbstat_unavailable']=str(e)
  prefix['file_minus_utf8_payload_bytes']=prefix['file_bytes']-prefix['utf8_payload_bytes'];write(out,'partial-layout.json',prefix)
  sys.path.insert(0,str(HERE));spec=importlib.util.spec_from_file_location('frozen_compare',HERE/'compare.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  tree=ast.parse((HERE/'compare.py').read_text());function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='catalog');before=ast.dump(function,include_attributes=False);changes=[]
  class Swap(ast.NodeTransformer):
   def visit_Call(self,node):
    if isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='sqlite3' and node.func.attr=='connect':
     assert ast.unparse(node)=="sqlite3.connect(r.out / 'catalog.sqlite')";changes.append(ast.dump(node,include_attributes=False));return ast.copy_location(ast.Name(id='writer',ctx=ast.Load()),node)
    return self.generic_visit(node)
  writer=Counter();rewritten=Swap().visit(function);assert len(changes)==1
  # Independently reverse the sole allowed substitution and prove complete AST equality.
  class Restore(ast.NodeTransformer):
   def visit_Name(self,node):
    if node.id=='writer':return ast.copy_location(ast.parse("sqlite3.connect(r.out / 'catalog.sqlite')",mode='eval').body,node)
    return node
  import copy
  restored=Restore().visit(copy.deepcopy(rewritten));assert ast.dump(restored,include_attributes=False)==before
  namespace=dict(vars(module));namespace['writer']=writer;exec(compile(ast.fix_missing_locations(ast.Module(body=[rewritten],type_ignores=[])),str(HERE/'compare.py'),'exec'),namespace)
  class Harness:
   def __init__(self):
    self.paths={k:Path(v['path']) for k,v in plan['inputs'].items()};self.out=out;self.stack=stack;self.adapter=module.load('frozen_adapter',self.paths['adapter']);self.receipt={}
   def guard(self,extra=0):assert sum(p.stat().st_size for p in out.iterdir() if p.is_file())<LIMIT
   def write(self,name,x):write(out,name,x)
  harness=Harness();namespace['catalog'](harness);measurement=writer.result();measurement['catalog_counts']=harness.receipt['counts'];measurement['exact_ast_change']='Only sqlite3.connect(r.out / catalog.sqlite) replaced by counting writer; every catalog decision, SQL INSERT tuple and original baseline reconstruction unchanged.';measurement['parent_catalog_ast_sha256']=hashlib.sha256(before.encode()).hexdigest();write(out,'complete-size.json',measurement);receipt['complete']=True
 except BaseException as e:receipt['error']=repr(e);raise
 finally:
  stack.close();receipt.update(seconds=time.monotonic()-start,memory={k:int(v.split()[0])*1024 for k,v in (s.split(':',1) for s in Path('/proc/self/status').read_text().splitlines() if s.startswith(('VmHWM:','VmPeak:')))},outputs={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in out.iterdir() if p.is_file()});write(out,'receipt.json',receipt);print(json.dumps(receipt,sort_keys=True),flush=True)
if __name__=='__main__':main()
