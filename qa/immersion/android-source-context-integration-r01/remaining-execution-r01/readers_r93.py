#!/usr/bin/env python3
"""Privileged read-only active/queued-consumer check. No service mutation."""
from pathlib import Path
import os,json,datetime,subprocess,pwd,argparse
TARGET='/home/ai/Development/investigations/vipi-android-readiness-20261107-r01/source-snapshot-r93/android/app/build/intermediates'
SNAPSHOT=TARGET.split('/android/app/build/')[0]
ROOT=Path('/home/ai/Development/investigations/vipi-android-source-context-integration-20261109-r01/retirement-r93-intermediates-r01')
assert os.geteuid()==0
uid=pwd.getpwnam('ai').pw_uid
own=set();pid=os.getpid()
while pid>1:
 own.add(pid)
 try:pid=int(Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()[1])
 except FileNotFoundError:break
matches=[];unreadable=[];processes=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 pid=int(p.name)
 try:
  argv=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
  if SNAPSHOT in argv and pid not in own:processes.append({'pid':pid,'reference':'snapshot in cmdline'})
  for item in [p/'cwd',p/'root',p/'exe',*list((p/'fd').iterdir())]:
   try:ref=os.readlink(item)
   except FileNotFoundError:continue
   if ref==TARGET or ref.startswith(TARGET+'/'):matches.append({'pid':pid,'kind':str(item.relative_to(p)),'path':ref})
  for line in (p/'maps').read_text().splitlines():
   if TARGET in line:matches.append({'pid':pid,'kind':'mapping','path':line.split(None,5)[-1]})
 except FileNotFoundError:pass
 except PermissionError:unreadable.append(pid)
def run(cmd):
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
 return {'cmd':cmd,'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
queue={}
for key,cmd in [('system_jobs',['systemctl','list-jobs','--no-pager','--no-legend']),('system_timers',['systemctl','list-timers','--all','--no-pager','--no-legend']),('at_queue',['sh','-c','if command -v atq >/dev/null; then atq; else echo atq_not_installed; fi']),('user_jobs',['sudo','-u','ai','env',f'XDG_RUNTIME_DIR=/run/user/{uid}',f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus','systemctl','--user','list-jobs','--no-pager','--no-legend']),('user_timers',['sudo','-u','ai','env',f'XDG_RUNTIME_DIR=/run/user/{uid}',f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus','systemctl','--user','list-timers','--all','--no-pager','--no-legend'])]:queue[key]=run(cmd)
# Exact reference search through installed service/timer/cron definitions. Static
# source scripts elsewhere are provenance, not queued consumers.
refs=[]
for base in ['/etc/systemd/system','/run/systemd/system','/home/ai/.config/systemd/user','/etc/cron.d','/var/spool/cron/crontabs']:
 d=Path(base)
 if not d.exists():continue
 for f in d.rglob('*'):
  try:
   if f.is_file() and not f.is_symlink() and f.stat().st_size<1048576 and SNAPSHOT in f.read_text(errors='replace'):refs.append(str(f))
  except (FileNotFoundError,PermissionError):pass
r={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'euid':os.geteuid(),'target':TARGET,'active_fd_cwd_maps':matches,'other_snapshot_cmdline_processes':processes,'permission_denied_pids':unreadable,'control_process_ancestry_excluded_from_cmdline_only':sorted(own),'queue_observations':queue,'installed_scheduler_definition_references':refs,'limit':'Instantaneous OS checks, not proof against future manual launches. Root ownership review and fresh repetition immediately before deletion required.'}
parser=argparse.ArgumentParser();parser.add_argument('--receipt-name',default='privileged-consumer-review-r03.json');args=parser.parse_args();assert Path(args.receipt_name).name==args.receipt_name
out=ROOT/args.receipt_name;assert not out.exists();out.write_text(json.dumps(r,indent=2)+'\n');os.chown(out,uid,pwd.getpwnam('ai').pw_gid)
print(json.dumps({'active_references':len(matches),'snapshot_processes':len(processes),'permission_denied':len(unreadable),'scheduler_refs':refs,'queue_exits':{k:v['exit'] for k,v in queue.items()},'receipt':str(out)}))
