import hashlib,json,os,shutil,socket,subprocess,time
from pathlib import Path
R=Path('/srv/fallsoft/staging/vipi-bilingual-occurrence-roles-20261109-r01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert socket.gethostname()=='fallsoft-production-20261106';p=json.loads((R/'protocol-r02.json').read_text());assert sha(Path(__file__))==p['runner_sha256'];assert (R/'runtime-amendment-authorization.json').is_file()
 approval=json.loads((R/'runtime-amendment-authorization.json').read_text());assert approval['protocol_sha256']==sha(R/'protocol-r02.json') and approval['authorized'] is True
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.nice(10);start=time.monotonic();out=R/'outputs-r02';out.mkdir(exist_ok=False);receipt={'complete':False,'protocol_sha256':sha(R/'protocol-r02.json'),'root_approval_sha256':sha(R/'runtime-amendment-authorization.json'),'limits':p['limits']}
 try:
  assert shutil.disk_usage(R).free>8*1024**3+64*1024**2
  for name,h in p['assets'].items():assert sha(R/name)==h,name
  classes=out/'classes';classes.mkdir();cp=str(R/'assets/opennlp-tools-2.5.10.jar')+':'+str(R/'assets/slf4j-api-2.0.18.jar')
  commands=[[p['java_home']+'/bin/javac','-J-Xmx256m','-J-XX:ActiveProcessorCount=1','--release','17','-cp',cp,'-d',str(classes),str(R/'BilingualRoleProbe.java')],[p['java_home']+'/bin/java','-Xms16m','-Xmx256m','-XX:ActiveProcessorCount=1','-cp',str(classes)+':'+cp,'BilingualRoleProbe',str(R/'assets/opennlp-en-ud-ewt-pos-1.3-2.5.4.bin'),str(R/'assets/opennlp-es-ud-gsd-pos-1.3-2.5.4.bin'),str(R/'inputs.tsv')]]
  receipt['commands']=commands
  for i,cmd in enumerate(commands):
   with (out/('compile.stdout' if i==0 else 'annotations.jsonl')).open('xb') as stdout,(out/('compile.stderr' if i==0 else 'run.stderr')).open('xb') as stderr:
    result=subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=max(1,120-(time.monotonic()-start)));assert result.returncode==0,(i,result.returncode)
  expected=json.loads((R/'endpoint-map.json').read_text());rows=[json.loads(s) for s in (out/'annotations.jsonl').read_text().splitlines()];assert len(rows)==len(expected)
  for row,e in zip(rows,expected):
   assert row['endpoint_key']==e['endpoint_key'] and row['language']==e['language'] and row['text_sha256']==e['text_sha256'];assert len(row['tokens'])==len(e['tokens'])
   for token,t in zip(row['tokens'],e['tokens']):assert token[:2]==t['utf16'] and isinstance(token[2],str) and 0<=token[3]<=1
  assert sum(x.stat().st_size for x in out.rglob('*') if x.is_file())<8*1024**2
  receipt.update(complete=True,endpoints=len(rows),supplied_tokens=sum(len(r['tokens']) for r in rows),metrics=(out/'run.stderr').read_text())
 except BaseException as e:receipt['error']=repr(e);raise
 finally:
  receipt.update(seconds=time.monotonic()-start,free_after=shutil.disk_usage(R).free,outputs={str(f.relative_to(out)):{'bytes':f.stat().st_size,'sha256':sha(f)} for f in out.rglob('*') if f.is_file()});(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
if __name__=='__main__':main()
