import hashlib,json,os,resource,shutil,socket,subprocess,time
from pathlib import Path
R=Path('/srv/fallsoft/staging/vipi-apertium-corpus-evidence-20261109-r01');A=Path('/srv/fallsoft/staging/vipi-apertium-occurrence-roles-20261109-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert socket.gethostname()=='fallsoft-production-20261106';assert shutil.disk_usage(R).free>8*1024**3+8*1024**2;os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2);start=time.monotonic();out=R/'batch-qualification-r02';out.mkdir(exist_ok=False);receipt={'complete':False,'script_sha256':sha(Path(__file__))};env=os.environ.copy();env['LD_LIBRARY_PATH']=str(A/'root/usr/lib/x86_64-linux-gnu');env['LC_ALL']='C.UTF-8';results=[]
 def execute(label,command,value):
  tick=time.monotonic();mem=0;stdout=out/(label+'.stdout');stderr=out/(label+'.stderr')
  with stdout.open('xb') as so,stderr.open('xb') as se:
   # Inputs below128KiB; communicate uses pipe handling without changing token bytes.
   child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=so,stderr=se,env=env)
   try:
    child.communicate(value,timeout=max(1,120-(time.monotonic()-start)))
   finally:
    if child.poll() is None:child.kill();child.wait()
  assert child.returncode==0,(label,child.returncode);assert sum(p.stat().st_size for p in out.iterdir() if p.is_file())<8*1024**2
  return stdout.read_bytes(),time.monotonic()-tick
 try:
  prior=json.loads((A/'outputs/receipt.json').read_text());assert prior['complete'];assert sha(A/'outputs/stages.jsonl')==prior['outputs']['stages.jsonl']['sha256'];rows=[json.loads(s) for s in (A/'outputs/stages.jsonl').read_text().splitlines()];assert len(rows)==64
  for language,direction in [('en','eng-spa'),('es','spa-eng')]:
   selected=[x for x in rows if x['language']==language];assert len(selected)==32
   for order in ('forward','reverse'):
    ordered=selected if order=='forward' else list(reversed(selected));value=b''.join(x['stages'][0]['output'].encode()+b'\x00' for x in ordered);assert value.count(b'\x00')==32
    commands=[[str(A/'root/usr/bin/lt-proc'),'-z',str(A/'root/usr/share/apertium/apertium-eng-spa'/(direction+'.automorf.bin'))],[str(A/'root/usr/bin/apertium-tagger'),'-g','-p','-z',str(A/'root/usr/share/apertium/apertium-eng-spa'/(direction+'.prob'))]]
    for stage,command in enumerate(commands,1):
     value,seconds=execute(f'{language}-{order}-{stage}',command,value);segments=value.split(b'\x00');trailing_empty=segments[-1]==b''
     if trailing_empty:segments=segments[:-1]
     comparisons=[{'endpoint_key':x['endpoint_key'],'expected_sha256':hashlib.sha256(x['stages'][stage]['output'].encode()).hexdigest(),'actual_sha256':hashlib.sha256(s).hexdigest(),'byte_equal':s==x['stages'][stage]['output'].encode()} for x,s in zip(ordered,segments)]
     results.append({'language':language,'order':order,'stage':stage,'command':command,'seconds':seconds,'expected_count':32,'segments':len(segments),'trailing_empty_after_NUL':trailing_empty,'all_byte_equal':len(segments)==32 and all(c['byte_equal'] for c in comparisons),'comparisons':comparisons})
  receipt.update(complete=True,all_byte_equal=all(x['all_byte_equal'] for x in results),results=results,reset_test='Forward and reversed endpoint order, exact per-endpoint byte parity for morphology and HMM disambiguation; unchanged deformatter output supplied separately.',deformatter_batching='Existing destxt help/man has no -z; deformat each endpoint separately, reuse exact per-endpoint stage contract. No implicit undocumented NUL assumption.' )
 except BaseException as e:receipt['error']=repr(e);raise
 finally:
  receipt.update(seconds=time.monotonic()-start,parent_VmHWM_bytes=int(next(s.split()[1] for s in Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:')))*1024,prior_stages_sha256=sha(A/'outputs/stages.jsonl'),outputs={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in out.iterdir() if p.is_file()});(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ('results','outputs')}));print([(x['language'],x['order'],x['stage'],x['segments'],x['all_byte_equal'],x['seconds']) for x in results])
if __name__=='__main__':main()
