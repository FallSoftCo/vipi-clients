from pathlib import Path
import os,json,hashlib,base64,subprocess,time,shutil,datetime
os.umask(0o077)
q=Path(__file__).resolve().parent;p=Path('/home/ai/Development/investigations/vipi-android-source-annotations-20261108-r01')
sha=lambda b:hashlib.sha256(b).hexdigest()
b=(q/'inputs.json').read_bytes();assert sha(b)=='cb37306db9723bf39ea41204674515c890fa12186d7e6ac052db06e6d1f27b14'
e=Path('/home/ai/Development/investigations/vipi-production-delivery-20261107/source-context-independent-expectations-r01.json');assert sha(e.read_bytes())=='191eb78e0cf07c3883520933542e127493da1aa746a1ef346823a740051129c8'
assert shutil.disk_usage(p).free>=8589934592
cases=json.loads(b)['cases'];assert len(cases)==116
enc=lambda s:base64.b64encode(s.encode()).decode()
tsv=''.join(enc(c['id'])+'\t'+enc(c['text'])+'\n' for c in cases);(p/'id-text.tsv').write_text(tsv)
cp=str(p/'opennlp-tools-2.5.10.jar')+':'+str(p/'slf4j-api-2.0.18.jar');cpu=min(os.sched_getaffinity(0));classes=p/'classes';classes.mkdir(exist_ok=False)
compile_cmd=['taskset','-c',str(cpu),'javac','-J-Xmx256m','-J-XX:ActiveProcessorCount=1','--release','17','-cp',cp,'-d',str(classes),str(q/'android-SourceProbe.java')]
run_cmd=['taskset','-c',str(cpu),'java','-Xms16m','-Xmx256m','-XX:ActiveProcessorCount=1','-cp',str(classes)+':'+cp,'SourceProbe',str(p)]
intent={'frozen_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inputs_sha256':sha(b),'model_input_sha256':sha(tsv.encode()),'source_sha256':sha((q/'android-SourceProbe.java').read_bytes()),'launcher_sha256':sha(Path(__file__).read_bytes()),'expectation_sha256':sha(e.read_bytes()),'compile_cmd':compile_cmd,'run_cmd':run_cmd,'before_output':True}
(p/'run-intent.json').write_text(json.dumps(intent,indent=2)+'\n'); start=time.monotonic(); receipt={}
try:
 with (p/'compile.stdout').open('w') as out,(p/'compile.stderr').open('w') as err:
  r=subprocess.run(compile_cmd,stdout=out,stderr=err,timeout=60);receipt['compile_returncode']=r.returncode
 assert r.returncode==0,'compile failed'
 assert shutil.disk_usage(p).free>=8589934592
 with (p/'annotations.jsonl').open('w') as out,(p/'run.stderr').open('w') as err:
  r=subprocess.run(run_cmd,stdout=out,stderr=err,timeout=min(120,180-(time.monotonic()-start)));receipt['run_returncode']=r.returncode
 assert r.returncode==0,'run failed'
 rows=[json.loads(l) for l in (p/'annotations.jsonl').read_text().splitlines()]; passes=[]
 for i in range(3):
  rs=[{k:v for k,v in r.items() if k!='pass'} for r in rows if r['pass']==i];assert len(rs)==116
  passes.append(sha(json.dumps(rs,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()))
 receipt.update(pass_content_sha256=passes,three_passes_equal=len(set(passes))==1,rows=len(rows),output_sha256=sha((p/'annotations.jsonl').read_bytes()))
except Exception as err:
 receipt['error']=repr(err)
finally:
 receipt.update(frozen_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),elapsed_compute_seconds=time.monotonic()-start,additional_file_bytes=sum(x.stat().st_size for x in p.rglob('*') if x.is_file()),free_bytes_after=shutil.disk_usage(p).free)
 (p/'run-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
