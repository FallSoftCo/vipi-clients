from pathlib import Path
import os,json,subprocess,time,signal,shutil,sys,hashlib
p=Path('/home/ai/Development/investigations/vipi-android-opennlp-runtime-20261108-r01');q=Path(__file__).resolve().parent;variant=sys.argv[1];assert variant in ['Debug','Release']
b={}
assert not (p/('build-'+variant+'-r03.json')).exists()
def allocation(path):return int(subprocess.check_output(['du','-sB1',str(path)],text=True).split()[0])
project0=allocation(p/'project');cache0=allocation(Path('/home/ai/.gradle/caches'));
free0=shutil.disk_usage(p).free;assert free0>8589934592+268435456
cmd=['taskset','-c',str(sorted(os.sched_getaffinity(0))[2]),'/home/ai/.gradle/wrapper/dists/gradle-8.13-bin/5xuhj0ry160q40clulazy9h7d/gradle-8.13/bin/gradle','--offline','--no-daemon','--max-workers=1','--console=plain','-PretainedAssets=/home/ai/Development/investigations/vipi-android-source-annotations-20261108-r01',':app:assemble'+variant]
x={'variant':variant,'cmd':cmd,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'free_before':free0,'success':False};(p/('build-'+variant+'-intent-r03.json')).write_text(json.dumps(x,indent=2)+'\n')
start=time.monotonic()
with (p/('build-'+variant+'-r03.log')).open('w') as log:proc=subprocess.Popen(cmd,cwd=p/'project',stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
try:
 while proc.poll() is None:
  free=shutil.disk_usage(p).free;x['min_free_bytes']=min(x.get('min_free_bytes',free),free)
  growth=max(0,allocation(p/'project')-project0)+max(0,allocation(Path('/home/ai/.gradle/caches'))-cache0);x['peak_project_plus_shared_cache_growth_bytes']=max(x.get('peak_project_plus_shared_cache_growth_bytes',0),growth)
  if free<8589934592 or growth>268435456 or time.monotonic()-start>240:raise RuntimeError('build budget/deadline')
  time.sleep(1)
 x['exit']=proc.returncode;x['success']=proc.returncode==0
except Exception as e:
 x['error']=repr(e)
 if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
finally:
 x['elapsed_seconds']=time.monotonic()-start;x['free_after']=shutil.disk_usage(p).free;(p/('build-'+variant+'-r03.json')).write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x,indent=2))
