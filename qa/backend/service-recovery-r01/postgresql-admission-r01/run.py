import pathlib,subprocess,os,shutil,time,json,signal
root=pathlib.Path('/home/ai/Development/.vipi-recovery-pg-20261111-r01');assert not root.exists();root.mkdir(mode=0o700)
base=pathlib.Path('/home/ai/Development/investigations/vipi-submit-20261110-r01/backend-restore-admission-pg-r01');pg='/usr/lib/postgresql/16/bin/';py='/home/ai/Development/investigations/vipi-production-delivery-20261107/backend-env/bin/python'
r={'floor':4*1024**3,'budget':256*1024**2,'free_before':shutil.disk_usage(root).free,'stages':[],'completed':False};assert r['free_before']>r['floor']+r['budget'];started=False
r['preexisting_postgres_pids']=subprocess.check_output(['pgrep','-x','postgres'],text=True).splitlines()
def save():(base/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
def run(name,args,limit=60):
 st={'name':name,'args':args};r['stages'].append(st);save();t=time.monotonic()
 with (base/(name+'.log')).open('wb') as f:
  p=subprocess.Popen(args,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  while p.poll() is None:
   used=int(subprocess.check_output(['du','-sb',str(root)],text=True).split()[0]);r['peak_owned_bytes']=max(r.get('peak_owned_bytes',0),used)
   free=shutil.disk_usage(root).free;r['min_free']=min(r.get('min_free',free),free)
   if free<r['floor'] or used>r['budget'] or time.monotonic()-t>limit:
    os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=10);raise RuntimeError('bounded job stop')
   time.sleep(.3)
 st.update(exit=p.returncode,seconds=time.monotonic()-t);save();assert p.returncode==0,name
try:
 run('initdb',[pg+'initdb','-D',str(root/'data'),'--auth-local=trust','--auth-host=reject','--no-locale','--encoding=UTF8'])
 (root/'socket').mkdir(mode=0o700)
 with (root/'data/postgresql.conf').open('a') as f:f.write("\nlisten_addresses=''\nunix_socket_directories='"+str(root/'socket')+"'\nunix_socket_permissions=0700\nmax_connections=10\nshared_buffers=16MB\nmin_wal_size=32MB\nmax_wal_size=32MB\n")
 run('start',[pg+'pg_ctl','-D',str(root/'data'),'-l',str(root/'postgres.log'),'-w','start'])
 started=True;r['owned_postgres_pid']=int((root/'data/postmaster.pid').read_text().splitlines()[0]);save()
 run('probe',[py,str(base/'probe.py')],90)
 r['completed']=True
except BaseException as e:r['error']=repr(e)
finally:
 if (root/'data/postmaster.pid').exists():
  stop=subprocess.run([pg+'pg_ctl','-D',str(root/'data'),'-m','fast','-w','stop'],capture_output=True,text=True,timeout=30);(base/'stop.log').write_text(stop.stdout+stop.stderr);r['owned_stop_exit']=stop.returncode
 for name in ['postgres.log','probe-result.json']:
  if (root/name).exists():shutil.copyfile(root/name,base/name)
 r['owned_pid_file_absent']=not (root/'data/postmaster.pid').exists()
 r['preexisting_pids_alive']=all(pathlib.Path('/proc/'+p).exists() for p in r['preexisting_postgres_pids'])
 if r['owned_pid_file_absent']:
  for name in ['data','socket']:
   if (root/name).exists():shutil.rmtree(root/name)
  r['regenerable_data_removed']=True
 r['free_after']=shutil.disk_usage(root).free;save();print(json.dumps(r))
