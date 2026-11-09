import hashlib,json,os,resource,shutil,socket,subprocess,time
from pathlib import Path
R=Path('/srv/fallsoft/staging/vipi-apertium-occurrence-roles-20261109-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert socket.gethostname()=='fallsoft-production-20261106';plan=json.loads((R/'protocol.json').read_text());assert sha(Path(__file__))==plan['runner_sha256'];assert sha(R/'packet.json')==plan['packet_sha256'];pre=json.loads((R/'runtime-preflight.json').read_text());assert pre['all_retained_file_bytes_verified'];assert all('not found' not in x['ldd_stdout'] for x in pre['dependency_checks'].values())
 assert shutil.disk_usage(R).free>8*1024**3+32*1024**2;os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2);start=time.monotonic();out=R/'outputs';out.mkdir(exist_ok=False);receipt={'complete':False,'protocol_sha256':sha(R/'protocol.json'),'runtime_preflight_sha256':sha(R/'runtime-preflight.json')};rows=[];E=os.environ.copy();E['LD_LIBRARY_PATH']=str(R/'root/usr/lib/x86_64-linux-gnu');E['LC_ALL']='C.UTF-8';peak=0
 try:
  for name,h in plan['execution_assets'].items():assert sha(R/name)==h,name
  endpoints=[];seen=set()
  for case in json.loads((R/'packet.json').read_text())['cases']:
   for side in ('source','target'):
    e=case['pair'][side];key=hashlib.sha256(json.dumps([e['language'],e['id'],e['text'],e['tokens']],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    if key not in seen:endpoints.append((key,e));seen.add(key)
  assert len(endpoints)==64
  with (out/'stages.jsonl').open('x') as dest:
   for index,(key,e) in enumerate(endpoints):
    direction='eng-spa' if e['language']=='en' else 'spa-eng';base=R/'root/usr/share/apertium/apertium-eng-spa';commands=[[str(R/'root/usr/bin/apertium-destxt')],[str(R/'root/usr/bin/lt-proc'),str(base/(direction+'.automorf.bin'))],[str(R/'root/usr/bin/apertium-tagger'),'-g','-p',str(base/(direction+'.prob'))]];value=(e['text']+'\n').encode();row={'endpoint_key':key,'language':e['language'],'id':e['id'],'text_sha256':hashlib.sha256(e['text'].encode()).hexdigest(),'stages':[]}
    for si,cmd in enumerate(commands):
     assert time.monotonic()-start<120;stdout=out/f'{index:02d}-{si}.stdout';stderr=out/f'{index:02d}-{si}.stderr';mem=0
     with stdout.open('xb') as so,stderr.open('xb') as se:
      child=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=so,stderr=se,env=E);child.stdin.write(value);child.stdin.close()
      try:
       while child.poll() is None:
        if time.monotonic()-start>120:raise TimeoutError('120s stage deadline')
        try:
         for line in Path(f'/proc/{child.pid}/status').read_text().splitlines():
          if line.startswith('VmHWM:'):mem=max(mem,int(line.split()[1])*1024)
        except FileNotFoundError:pass
        time.sleep(.002)
      finally:
       if child.poll() is None:child.kill();child.wait()
     assert child.returncode==0,(key,si,child.returncode);peak=max(peak,mem);value=stdout.read_bytes();row['stages'].append({'command':cmd,'stdout_file':stdout.name,'stderr_file':stderr.name,'output':value.decode(),'stderr':stderr.read_text(),'observed_child_VmHWM_bytes':mem})
    rows.append(row);dest.write(json.dumps(row,ensure_ascii=False)+'\n');dest.flush();assert sum(p.stat().st_size for p in out.iterdir() if p.is_file())<8*1024**2
  receipt.update(complete=True,endpoints=len(rows),observed_max_child_VmHWM_bytes=peak)
 except BaseException as e:receipt['error']=repr(e);raise
 finally:
  receipt.update(seconds=time.monotonic()-start,parent_VmHWM_bytes=int(next(s.split()[1] for s in Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:')))*1024,outputs={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in out.iterdir() if p.is_file()});(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k!='outputs'}))
if __name__=='__main__':main()
