from pathlib import Path
import os,json,hashlib,base64,subprocess,time,shutil,datetime
os.umask(0o077)
q=Path(__file__).resolve().parent;p=Path('/home/ai/Development/investigations/vipi-source-role-veto-20261108-r01/android');p.mkdir(mode=0o700,exist_ok=False)
m=Path('/home/ai/Development/investigations/vipi-android-source-annotations-20261108-r01')
sha=lambda b:hashlib.sha256(b).hexdigest();b=(p.parent/'inputs.json').read_bytes();assert sha(b)=='c0ee9c86f35828b3309ab7278dcb0ce1d702fa168ec47e9bd91fd0ea3fa1df54'
protocol=(q/'comparison-protocol.json').read_bytes();assert sha(protocol)=='f4f22f184a7f05bc7fea15d17fd028951e38b7795d6afdd7818ffa36d98d145b'
assert shutil.disk_usage(p).free>=8589934592
pins={'opennlp-tools-2.5.10.jar':'123ee5aa02f8d8ab9b554fb927ae5003e0413bf066cc957094d3aeb304fb94ea','slf4j-api-2.0.18.jar':'44508fd1576500688c790b190acdd16fec4f8c79a3e0b900afd70503cf055f55','opennlp-en-ud-ewt-pos-1.3-2.5.4.bin':'510b89087e7ef7ffb8c50c63e3e999122404ac9fa64790dfa93b38d1938c52ce','opennlp-en-ud-ewt-tokens-1.3-2.5.4.bin':'95139111197ba9f1165fc12be8d4cbac05ea3912f995d167efa1a0e04e3e649a','opennlp-en-ud-ewt-sentence-1.3-2.5.4.bin':'4de58d12b09421003c8b1ba13e8b58ec533b28e1f22a65272119dc0993d333e8'}
for n,h in pins.items():assert sha((m/n).read_bytes())==h,n
cases=json.loads(b)['cases'];assert len(cases)==9535;assert max(len(c['text'].encode('utf-16-le'))//2 for c in cases)<=180
enc=lambda s:base64.b64encode(s.encode()).decode();tsv=''.join(enc(c['id'])+'\t'+enc(c['text'])+'\n' for c in cases);(p/'id-text.tsv').write_text(tsv)
cp=str(m/'opennlp-tools-2.5.10.jar')+':'+str(m/'slf4j-api-2.0.18.jar');cpu=min(os.sched_getaffinity(0));classes=p/'classes';classes.mkdir()
compile_cmd=['taskset','-c',str(cpu),'javac','-J-Xmx256m','-J-XX:ActiveProcessorCount=1','--release','17','-cp',cp,'-d',str(classes),str(q/'android-SourceRoleProbe.java')]
run_cmd=['taskset','-c',str(cpu),'java','-Xms16m','-Xmx256m','-XX:ActiveProcessorCount=1','-cp',str(classes)+':'+cp,'SourceRoleProbe',str(m),str(p)]
intent={'schema':'vipi.opennlp9535-source-freeze.r01','frozen_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'input_sha256':sha(b),'model_input_sha256':sha(tsv.encode()),'fields':['id','text'],'source_sha256':sha((q/'android-SourceRoleProbe.java').read_bytes()),'launcher_sha256':sha(Path(__file__).read_bytes()),'protocol_sha256':sha(protocol),'verified_assets':pins,'compile_cmd':compile_cmd,'run_cmd':run_cmd,'before_output':True,'limits':{'CPU':1,'JVM_heap_MiB':256,'total_compute_seconds':180,'output_bytes':16777216,'additional_bytes':33554432,'disk_free_floor_bytes':8589934592},'scope':'Linux JVM source-only annotations; no target labels or Android runtime claim'}
(q/'android-freeze.json').write_text(json.dumps(intent,indent=2)+'\n');(p/'freeze.json').write_text(json.dumps(intent,indent=2)+'\n');start=time.monotonic();receipt={}
try:
 with (p/'compile.stdout').open('w') as out,(p/'compile.stderr').open('w') as err:r=subprocess.run(compile_cmd,stdout=out,stderr=err,timeout=30);receipt['compile_returncode']=r.returncode
 assert r.returncode==0,'compile failed';assert shutil.disk_usage(p).free>=8589934592
 with (p/'annotations.jsonl').open('w') as out,(p/'run.stderr').open('w') as err:r=subprocess.run(run_cmd,stdout=out,stderr=err,timeout=180-(time.monotonic()-start));receipt['run_returncode']=r.returncode
 assert r.returncode==0,'run failed'
 rows=[json.loads(l) for l in (p/'annotations.jsonl').read_text().splitlines()];full=[r for r in rows if r['pass']==0];repeat=[r for r in rows if r['pass']==1];assert len(full)==9535 and len(repeat)==20
 assert [{k:v for k,v in r.items() if k!='pass'} for r in full[:20]]==[{k:v for k,v in r.items() if k!='pass'} for r in repeat]
 token_count=0
 for r,c in zip(full,cases):
  assert r['id']==c['id'] and r['source_sha256']==sha(c['text'].encode());u=c['text'].encode('utf-16-le');previous=0
  for a,z,tag,score in r['tokens']:
   assert 0<=a<z<=len(u)//2 and a>=previous;u[a*2:z*2].decode('utf-16-le');previous=z;token_count+=1
 receipt.update(full_count=len(full),repeat_count=len(repeat),first20_repeat_identical=True,tokens_checked=token_count,original_source_sha_and_UTF16_boundaries_verified=True,substring_check='Java verified every emitted tokenizer word against exact original substring; Python independently verified sourceSHA and all UTF16 boundaries.',output_sha256=sha((p/'annotations.jsonl').read_bytes()),output_bytes=(p/'annotations.jsonl').stat().st_size)
except Exception as err:receipt['error']=repr(err)
finally:
 receipt.update(frozen_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),elapsed_compute_seconds=time.monotonic()-start,additional_file_bytes=sum(x.stat().st_size for x in p.rglob('*') if x.is_file()),free_bytes_after=shutil.disk_usage(p).free,private_output=str(p/'annotations.jsonl'),input_sha256=sha(b),freeze_sha256=sha((q/'android-freeze.json').read_bytes()),platform='Linux OpenJDK21; Android native R8/runtime untested')
 (p/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');(q/'android-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
