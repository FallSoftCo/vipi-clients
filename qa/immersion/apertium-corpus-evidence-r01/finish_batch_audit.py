import hashlib,json,os,resource,subprocess,time
from pathlib import Path
R=Path('/srv/fallsoft/staging/vipi-apertium-corpus-evidence-20261109-r01');A=Path('/srv/fallsoft/staging/vipi-apertium-occurrence-roles-20261109-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2);start=time.monotonic();out=R/'batch-framing-audit';out.mkdir(exist_ok=False);prior=R/'batch-qualification-r02';receipt=json.loads((prior/'receipt.json').read_text());rows=[json.loads(s) for s in (A/'outputs/stages.jsonl').read_text().splitlines()];checks=[]
for item in receipt['results']:
 name=f"{item['language']}-{item['order']}-{item['stage']}.stdout";assert sha(prior/name)==receipt['outputs'][name]['sha256'];segments=(prior/name).read_bytes().split(b'\0');selected=[r for r in rows if r['language']==item['language']]
 if item['order']=='reverse':selected.reverse()
 assert len(selected)==32 and len(segments)>=32;assert all(segments[i]==r['stages'][item['stage']]['output'].encode() for i,r in enumerate(selected));assert all(s==b'' for s in segments[32:]);checks.append({'file':name,'sha256':sha(prior/name),'expected_records':32,'endpoint_records_byte_equal':32,'extra_empty_split_segments':len(segments)-32,'nonempty_extras':0})
packet=json.loads((A/'packet.json').read_text());endpoints={}
for c in packet['cases']:
 for side in ('source','target'):
  e=c['pair'][side];key=hashlib.sha256(json.dumps([e['language'],e['id'],e['text'],e['tokens']],ensure_ascii=False,sort_keys=True).encode()).hexdigest();endpoints[key]=e
E=os.environ.copy();E['LD_LIBRARY_PATH']=str(A/'root/usr/lib/x86_64-linux-gnu');E['LC_ALL']='C.UTF-8';tick=time.monotonic();times=[]
for row in rows:
 t=time.monotonic();e=endpoints[row['endpoint_key']];r=subprocess.run([str(A/'root/usr/bin/apertium-destxt')],input=(e['text']+'\n').encode(),capture_output=True,env=E,timeout=max(1,120-(time.monotonic()-start)));assert r.returncode==0 and r.stdout==row['stages'][0]['output'].encode();times.append({'endpoint_key':row['endpoint_key'],'seconds':time.monotonic()-t,'output_sha256':hashlib.sha256(r.stdout).hexdigest(),'byte_equal':True})
result={'original_strict_receipt_sha256':sha(prior/'receipt.json'),'original_all_byte_equal':receipt['all_byte_equal'],'endpoint_content_byte_parity':True,'only_terminal_empty_framing_records':True,'checks':checks,'deformatter':{'endpoints':64,'seconds':time.monotonic()-tick,'all_byte_equal':True,'timings':times,'custom_deformatter':False},'seconds':time.monotonic()-start,'parent_VmHWM_bytes':int(next(s.split()[1] for s in Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:')))*1024,'script_sha256':sha(Path(__file__))};(out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('checks','deformatter')}));print('deformat_seconds',result['deformatter']['seconds'])
