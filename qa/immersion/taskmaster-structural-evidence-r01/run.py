import collections,hashlib,importlib.util,json,os,resource,shutil,signal,socket,subprocess,sys,time
from pathlib import Path
R=Path('/srv/fallsoft/staging/vipi-taskmaster-structural-evidence-20261109-r01');A=Path('/srv/fallsoft/staging/vipi-apertium-occurrence-roles-20261109-r01');MiB=1<<20
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads(Path(p).read_text())
def main():
 assert socket.gethostname()=='fallsoft-production-20261106';p=load(R/'protocol.json');assert sha(__file__)==p['code_sha256'];os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(1<<30,)*2);resource.setrlimit(resource.RLIMIT_CPU,(300,300));signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('300s')));signal.alarm(300)
 out=R/'engine';out.mkdir(exist_ok=False);start=time.monotonic();receipt={'complete':False,'protocol_sha256':sha(R/'protocol.json'),'children':[]};child=None
 def total():return sum(f.stat().st_size for f in out.rglob('*') if f.is_file())
 def save(n,b):
  if not isinstance(b,bytes):b=(json.dumps(b,ensure_ascii=False,indent=2)+'\n').encode()
  assert total()+len(b)<=64*MiB,'output cap';f=out/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
 def call(cmd,value,label):
  nonlocal child
  t=time.monotonic();child=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,start_new_session=True)
  try:stdout,stderr=child.communicate(value,timeout=min(15,max(1,295-(time.monotonic()-start))))
  except BaseException:
   os.killpg(child.pid,signal.SIGKILL);child.wait();raise
  z=child.returncode;child=None;save(label+'.raw',stdout);save(label+'.stderr',stderr);receipt['children'].append({'label':label,'command':cmd,'exit_code':z,'seconds':time.monotonic()-t});assert z==0,(label,z,stderr.decode());return stdout
 try:
  receipt['free_before']=shutil.disk_usage(R).free;assert receipt['free_before']>8*(1<<30)+128*MiB
  for f,h in p['inputs'].items():assert sha(R/'inputs'/f)==h,f
  prior=load(A/'protocol.json')
  for f,h in prior['execution_assets'].items():assert sha(A/f)==h,f
  helper=R/'inputs/stream_helper.py';spec=importlib.util.spec_from_file_location('helper',helper);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h);assert h.controls()
  b=A/'root/usr/bin';d=A/'root/usr/share/apertium/apertium-eng-spa';env=dict(os.environ,LD_LIBRARY_PATH=str(A/'root/usr/lib/x86_64-linux-gnu'),LC_ALL='C.UTF-8')
  deps={}
  for name in ['lt-proc','apertium-tagger','apertium-pretransfer','lrx-proc','apertium-transfer','apertium-interchunk','apertium-postchunk','apertium-destxt']:
   z=subprocess.run(['ldd',str(b/name)],capture_output=True,text=True,env=env,timeout=10);assert z.returncode==0 and 'not found' not in z.stdout;(deps.update({name:z.stdout}))
  save('dependency-check.json',deps)
  rows=load(R/'inputs/inputs-200.json')['cases'];assert len(rows)==200 and len({x['id'] for x in rows})==200
  qual=set(sorted([r['id'] for r in rows],key=lambda i:hashlib.sha256(('taskmaster-structural-normal-parity\0'+i).encode()).hexdigest())[:16]);save('qualification-selection.json',sorted(qual));maps=[];last=time.monotonic()
  for i,row in enumerate(rows):
   key=f'{i:03d}';text=row['text'];assert '\0' not in text;prefix='stages/'+key+'/'
   dest=call([str(b/'apertium-destxt')],text.encode(),prefix+'destxt');morph=call([str(b/'lt-proc'),str(d/'eng-spa.automorf.bin')],dest,prefix+'morph');tag=call([str(b/'apertium-tagger'),'-g','-p',str(d/'eng-spa.prob')],morph,prefix+'tag');normal=h.strip_surface(tag.decode()).encode();save(prefix+'normal.raw',normal)
   if row['id'] in qual:assert call([str(b/'apertium-tagger'),'-g',str(d/'eng-spa.prob')],morph,prefix+'normal-check')==normal
   values={'normal':normal};value=normal
   commands=[('pretransfer',[str(b/'apertium-pretransfer')]),('genitive',[str(b/'apertium-transfer'),'-n','-T',str(d/'apertium-eng-spa.eng-spa.genitive.t1x'),str(d/'eng-spa.genitive.bin')]),('biltrans',[str(b/'lt-proc'),'-b',str(d/'eng-spa.autobil.bin')]),('lexical',[str(b/'lrx-proc'),'-m','-t',str(d/'eng-spa.autolex.bin')]),('chunk',[str(b/'apertium-transfer'),'-b','-T',str(d/'apertium-eng-spa.eng-spa.t1x'),str(d/'eng-spa.t1x.bin')]),('interchunk',[str(b/'apertium-interchunk'),'-t',str(d/'apertium-eng-spa.eng-spa.t2x'),str(d/'eng-spa.t2x.bin')]),('postchunk',[str(b/'apertium-postchunk'),'-t',str(d/'apertium-eng-spa.eng-spa.t3x'),str(d/'eng-spa.t3x.bin')])]
   for name,cmd in commands:value=call(cmd,value,prefix+name);values[name]=value
   source=[u['fields'][0] for u in h.units(normal.decode())];checks={s:[u['fields'][0] for u in h.units(values[s].decode())]==source for s in ['pretransfer','genitive','biltrans','lexical']}
   maps.append({'id':row['id'],'stage_prefix':prefix,'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'source_spans':h.source_spans(tag.decode(),text),'source_analyses':source,'sequence_identity':checks,'mapped':all(checks.values()),'before':[u['fields'][1:] for u in h.units(values['biltrans'].decode())],'after':[u['fields'][1:] for u in h.units(values['lexical'].decode())]})
   if time.monotonic()-last>40:print(json.dumps({'rows':i+1,'seconds':time.monotonic()-start,'bytes':total()}),flush=True);last=time.monotonic()
  save('mapping.json',maps);receipt['complete']=True;receipt['normal_parity_cases']=16;receipt['messages']=200
 except BaseException as e:receipt['error']=repr(e)
 finally:
  if child is not None:
   os.killpg(child.pid,signal.SIGKILL);child.wait()
  signal.alarm(0);receipt.update(seconds=time.monotonic()-start,VmHWM_bytes=int(next(x.split()[1] for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmHWM:')))*1024,child_peak_rss_bytes=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*1024,free_after=shutil.disk_usage(R).free)
  receipt['files']={str(f.relative_to(out)):{'bytes':f.stat().st_size,'sha256':sha(f)} for f in out.rglob('*') if f.is_file()};save('receipt.json',receipt);print(json.dumps({k:v for k,v in receipt.items() if k not in ['children','files']}),flush=True)
 if not receipt['complete']:sys.exit(1)
if __name__=='__main__':main()
