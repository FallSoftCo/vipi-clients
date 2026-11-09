#!/usr/bin/env python3
"""Read-only candidate inventory; never deletes files or changes runtime state."""
from pathlib import Path
import os,stat,json,hashlib,datetime,subprocess,time
TARGET=Path('/home/ai/Development/investigations/vipi-android-readiness-20261107-r01/source-snapshot-r93/android/app/build/intermediates')
ROOT=Path('/home/ai/Development/investigations/vipi-android-source-context-integration-20261109-r01/retirement-r93-intermediates-r01')
start=time.monotonic()
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1024*1024):
   h.update(b);assert time.monotonic()-start<120
 return h.hexdigest()
ROOT.mkdir(exist_ok=False)
assert TARGET.is_dir() and not TARGET.is_symlink() and TARGET.resolve()==TARGET
files=[];groups={};symlinks=[]
for p in sorted(TARGET.rglob('*')):
 s=p.lstat()
 if stat.S_ISLNK(s.st_mode):symlinks.append(str(p));continue
 if not stat.S_ISREG(s.st_mode):continue
 row={'path':str(p),'bytes':s.st_size,'allocated_bytes':s.st_blocks*512,'device':s.st_dev,'inode':s.st_ino,'nlink':s.st_nlink,'mtime_ns':s.st_mtime_ns,'sha256':digest(p)}
 assert p.stat().st_mtime_ns==s.st_mtime_ns and p.stat().st_size==s.st_size
 files.append(row);groups.setdefault((s.st_dev,s.st_ino),[]).append(row)
assert not symlinks
external=[v for v in groups.values() if v[0]['nlink']>len(v)]
reclaimable=sum(v[0]['allocated_bytes'] for v in groups.values() if v[0]['nlink']==len(v))
# Preserve current snapshot source, including any later QA overlays. Do not infer
# it is unchanged from r93's original manifest.
snapshot=TARGET.parents[3];preserved={}
for branch in ['android','scripts','qa']:
 for p in sorted((snapshot/branch).rglob('*')):
  rel=p.relative_to(snapshot)
  if any(x in {'build','.gradle','.cxx'} for x in rel.parts) or not p.is_file() or p.is_symlink():continue
  preserved[str(rel)]={'bytes':p.stat().st_size,'sha256':digest(p)}
receipts={}
evidence=snapshot.parent
for p in sorted(evidence.iterdir()):
 if p.is_file() and ('r93' in p.name or p.name in {'source-authority.json','README.md'}):receipts[str(p)]={'bytes':p.stat().st_size,'sha256':digest(p)}
for p in [evidence/'invalid-result-cache-r01/candidate-r98/main.apk',evidence/'invalid-result-cache-r01/candidate-r98/test.apk']:
 assert p.is_file();receipts[str(p)]={'bytes':p.stat().st_size,'sha256':digest(p)}
for branch in ['generated','outputs']:
 base=TARGET.parent/branch;receipts[str(base)]={'preserved':True,'exists':base.is_dir(),'files':sum(p.is_file() for p in base.rglob('*'))}
plan={'schema':'vipi.r93-intermediates-retirement-candidate.r01','at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'target':str(TARGET),'operation':'proposed_exact_listed_regular_files_only; NOT EXECUTED','files':files,'symlinks':symlinks,'unique_inodes':len(groups),'external_link_groups':external,'unique_logical_bytes':sum(v[0]['bytes'] for v in groups.values()),'reclaimable_allocated_file_bytes':reclaimable,'directory_blocks_not_counted':True,'preserved_current_snapshot_source':preserved,'preserved_original_receipts_and_accepted_artifacts':receipts,'reconstruction':'Current snapshot source/dependency assets remain; this directory contains AGP generated intermediate outputs, not authoritative source. Source overlays preserved as currently found. Current clean app compilation is independently complete and does not use this old tree.','requires_before_deletion':['root review of exact plan hash','fresh same-stat/hash candidate validation','privileged readers/maps/cwd + process/queued-consumer exclusion','confirmation preserved source and current compilation remain intact'],'seconds':time.monotonic()-start}
(ROOT/'candidate-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
print(json.dumps({'plan':str(ROOT/'candidate-plan.json'),'sha256':digest(ROOT/'candidate-plan.json'),'files':len(files),'unique_inodes':len(groups),'external_link_groups':len(external),'reclaimable_allocated_bytes':reclaimable,'preserved_source_files':len(preserved),'seconds':time.monotonic()-start}))
