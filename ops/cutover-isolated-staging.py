#!/usr/bin/env python3
"""Prepare then activate Vipi's isolated identity pool, preserving the old DB.

No package installation, firewall change, shared service restart or old-user
deletion. Only Vipi restarts; nginx uses a validated graceful reload. Preparation
and activation are separate, retained steps. Never repeat an uncertain stage.
"""
import argparse
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.dont_write_bytecode=True

BASE=Path('/opt/vipi/isolated-staging-001')
DATABASE='vipi_isolated_001'
CLIENT='client_01M5S2CDSQ8F7FEX26G3CY9VS1'
ENVIRONMENT='environment_01M5S2CDCTMYJ46EBGXYWS5KBC'
OWNER='01a16e0d-ac69-7dd0-872a-8cf087160515'
ENV_FILE=Path('/etc/vipi/service.env')
UNIT=Path('/etc/systemd/system/vipi-api.service')
NGINX=Path('/etc/nginx/sites-available/vipi-api')


def require(ok,message):
    if not ok: raise RuntimeError(message)


def run(command,*,env=None,cwd=None,timeout=60):
    return subprocess.check_output(command,env=env,cwd=cwd,timeout=timeout,text=True,stderr=subprocess.STDOUT)


def sql(statement,database='postgres'):
    return run(['runuser','-u','postgres','--','psql','-X','-v','ON_ERROR_STOP=1','-At','-d',database,'-c',statement]).strip()


def save(value):
    tmp=BASE/'receipt.tmp'
    with tmp.open('w') as out:
        json.dump(value,out,indent=2);out.write('\n');out.flush();os.fsync(out.fileno())
    tmp.chmod(0o600);tmp.replace(BASE/'receipt.json')


def digest(file): return hashlib.sha256(file.read_bytes()).hexdigest()


def fetch(url):
    try:
        with urllib.request.urlopen(url,timeout=5) as response:
            return response.status,response.read(65536),response.headers
    except urllib.error.HTTPError as error:
        return error.code,error.read(65536),error.headers


def protected():
    units=run(['systemctl','list-units','--type=service','--state=running','--no-legend','--plain']).splitlines()
    result={}
    for line in units:
        name=line.split()[0]
        if name.startswith('vipi-'): continue
        values=dict(v.split('=',1) for v in run(['systemctl','show',name,'--property=MainPID,ActiveEnterTimestampMonotonic,Type']).splitlines())
        if values['Type']!='oneshot' and values['MainPID']!='0': result[name]=values
    return result


def verify_protected(before):
    after=protected()
    require(all(after.get(name)==value for name,value in before.items()),'A protected service identity changed; inspect before further work')
    return after


def await_ready(port):
    deadline=time.monotonic()+25
    while time.monotonic()<deadline:
        try:
            status,body,_=fetch(f'http://127.0.0.1:{port}/health/ready')
            if status==200 and json.loads(body)=={'status':'ok'}: return
        except (OSError,ValueError): pass
        time.sleep(.3)
    raise RuntimeError('Vipi readiness did not recover')


def install_file(source,target,mode=0o644,group=None):
    temp=target.with_name(target.name+'.vipi-next')
    require(not temp.exists(),'Another file installation is pending')
    shutil.copyfile(source,temp);temp.chmod(mode)
    if group is not None: os.chown(temp,0,group)
    os.replace(temp,target)


def activate_link(release):
    temp=Path('/opt/vipi/current.next')
    require(not temp.exists() and not temp.is_symlink(),'Another release activation is pending')
    temp.symlink_to(release);os.replace(temp,'/opt/vipi/current')


def main(args):
    require(socket.gethostname()=='ubuntu-16gb-ash-1' and os.geteuid()==0,'Wrong host or user')
    require(re.fullmatch(r'[0-9a-f]{40}',args.revision) and re.fullmatch(r'[0-9a-f]{40}',args.expected_current),'Invalid source revision')
    new=Path('/opt/vipi/releases')/args.revision
    old=Path('/opt/vipi/releases')/args.expected_current
    spec=importlib.util.spec_from_file_location('vipi_upgrade',new/'ops/upgrade-service.py')
    upgrade=importlib.util.module_from_spec(spec);spec.loader.exec_module(upgrade)
    upgrade.verify_release(new,args.revision);upgrade.verify_release(old,args.expected_current)
    require(Path('/opt/vipi/current').resolve()==old,'Current release changed')
    require(sql('SELECT version_num FROM alembic_version','vipi')=='20261025_01','Old schema changed')
    require(fetch('http://127.0.0.1:48943/health/ready')[0]==200,'Existing Vipi is unhealthy')
    config_text=run(['nginx','-T'])
    require(not re.search(r'\bworker_shutdown_timeout\s+(?!0(?:s)?;)',config_text),'Shared nginx has a forced worker shutdown deadline')
    if args.action=='stage':
        require(not BASE.exists(),'Preparation already exists; inspect its receipt instead of repeating')
        require(not sql(f"SELECT datname FROM pg_database WHERE datname='{DATABASE}'"),'Destination DB already exists')
        require(shutil.disk_usage('/opt/vipi').free>2*1024**3,'Insufficient deployment headroom')
        private=json.loads(Path(args.private_config).read_text())
        require(private['client_id']==CLIENT and private['environment_id']==ENVIRONMENT,'Wrong WorkOS pool')
        require(private['workos_api_key'].startswith('sk_test_'),'Staging API key required')
        require(len(private['subjects'])==3 and len(set(private['subjects']))==3,'Expected exactly three controlled QA subjects')
        for subject in private['subjects']:
            require(re.fullmatch(r'user_[A-Za-z0-9]+',subject),'Invalid QA subject')
            request=urllib.request.Request('https://api.workos.com/user_management/users/'+subject,
                headers={'Authorization':'Bearer '+private['workos_api_key']})
            with urllib.request.urlopen(request,timeout=10) as response: person=json.load(response)
            require(person['id']==subject and person.get('metadata',{}).get('vipi_qa_run','').startswith('vipi-isolated-'),'Unverified QA identity')
        BASE.mkdir(mode=0o700)
        receipt={'owner':OWNER,'host':socket.gethostname(),'old_revision':args.expected_current,'new_revision':args.revision,
            'database':DATABASE,'old_database_preserved':'vipi','cohort_run':private['cohort_run'],'subject_count':3,
            'created_at':datetime.now(UTC).isoformat(),'state':'preparing','protected_before':protected(),'steps':[]}
        save(receipt)
        try:
            for source,name in [(ENV_FILE,'old.env'),(UNIT,'old.service'),(NGINX,'old.nginx')]:
                shutil.copyfile(source,BASE/name);(BASE/name).chmod(0o600)
            receipt['old_hashes']={str(p):digest(p) for p in [ENV_FILE,UNIT,NGINX]};save(receipt)
            (BASE/'new.nginx').write_text((new/'ops/nginx-api-http.conf').read_text()+'\n'+(new/'ops/nginx-api-https.conf').read_text())
            require('root /var/lib/vipi-acme;' in (BASE/'new.nginx').read_text(),'ACME webroot missing')
            sql(f'CREATE DATABASE {DATABASE} OWNER vipi_owner')
            sql(f'REVOKE ALL ON DATABASE {DATABASE} FROM PUBLIC; GRANT CONNECT ON DATABASE {DATABASE} TO vipi')
            receipt['steps'].append('separate_database_created');save(receipt)
            env=os.environ.copy();env.update(PYTHONPATH=str(new/'deps'),PYTHONDONTWRITEBYTECODE='1',
                VIPI_DATABASE_URL=f'postgresql+asyncpg://postgres@/{DATABASE}?host=/var/run/postgresql',VIPI_MIGRATION_ROLE='vipi_owner')
            run(['runuser','-u','postgres','--','/usr/bin/python3','-m','alembic','-c',str(new/'alembic.ini'),'upgrade','head'],env=env,cwd=new)
            sql('REVOKE ALL ON SCHEMA public FROM PUBLIC; GRANT USAGE ON SCHEMA public TO vipi; '
                'GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO vipi; '
                'REVOKE INSERT,UPDATE,DELETE ON alembic_version FROM vipi; '
                'GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO vipi',DATABASE)
            require(sql("SELECT has_schema_privilege('vipi','public','CREATE'),pg_has_role('vipi','vipi_owner','MEMBER')",DATABASE)=='f|f','Runtime gained DDL privileges')
            require(sql('SELECT version_num FROM alembic_version',DATABASE)=='20261025_02','Wrong new schema')
            values={'VIPI_DATABASE_URL':f'postgresql+asyncpg://vipi@/{DATABASE}?host=/var/run/postgresql',
                'VIPI_WORKOS_CLIENT_ID':CLIENT,'VIPI_WORKOS_ISSUER':'https://api.workos.com','VIPI_SERVICE_SECRET':secrets.token_urlsafe(32),
                'VIPI_ENVIRONMENT':'staging','VIPI_ALLOWED_SUBJECTS':json.dumps(private['subjects'],separators=(',',':')),
                'VIPI_ACCOUNT_DELETION_ENABLED':'true','VIPI_WORKOS_DEDICATED_USER_POOL':'true',
                'VIPI_WORKOS_API_KEY':private['workos_api_key'],'VIPI_DELETION_WEB_ORIGIN':'https://api.mambovipi.app'}
            (BASE/'new.env').write_text('\n'.join(key+'='+repr(value) for key,value in values.items())+'\n');(BASE/'new.env').chmod(0o600)
            receipt['steps'].append('new_schema_and_private_configuration_prepared');save(receipt)
            with socket.socket() as probe: probe.bind(('127.0.0.1',48944))
            env.update(values);env.pop('VIPI_MIGRATION_ROLE',None)
            with (BASE/'candidate.log').open('w') as log:
                process=subprocess.Popen(['runuser','-u','vipi','--','/usr/bin/python3','-m','uvicorn','vipi.entrypoint:app',
                    '--host','127.0.0.1','--port','48944','--no-access-log','--log-level','warning'],env=env,cwd=new,
                    stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                try:
                    await_ready(48944)
                    require(fetch('http://127.0.0.1:48944/v1/me')[0]==401,'Candidate authentication bypass')
                    status,body,head=fetch('http://127.0.0.1:48944/delete-account')
                    require(status==200 and b'Delete your Vipi account' in body and head['Referrer-Policy']=='same-origin','Candidate browser route failed')
                    require(fetch('http://127.0.0.1:48944/delete-account/style.css')[0]==200,'Packaged CSS missing')
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid,signal.SIGTERM)
                        try: process.wait(timeout=10)
                        except subprocess.TimeoutExpired: os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
            receipt['steps'].append('packaged_candidate_qualified_and_listener_stopped')
            receipt['protected_after_stage']=verify_protected(receipt['protected_before'])
            receipt['state']='prepared';save(receipt)
        except BaseException as error:
            receipt['state']='preparation_failed';receipt['failure_type']=type(error).__name__;save(receipt);raise
    else:
        receipt=json.loads((BASE/'receipt.json').read_text())
        require(receipt['state']=='prepared' and receipt['new_revision']==args.revision and receipt['old_revision']==args.expected_current,'Preparation mismatch')
        require(all(digest(Path(p))==value for p,value in receipt['old_hashes'].items()),'Installed configuration changed after preparation')
        require(sql('SELECT count(*) FROM account_deletions',DATABASE)=='0','Unexpected deletion work before activation')
        require(run(['systemctl','is-active','vipi-expiry.timer']).strip()=='active','Expiry timer state changed')
        before=protected();receipt['protected_before_apply']=before;receipt['state']='activating';save(receipt)
        group=pwd.getpwnam('vipi').pw_gid
        try:
            run(['systemctl','stop','vipi-expiry.timer'])
            # No new timer launches; an already running bounded maintenance task
            # finishes normally before the environment file changes.
            deadline=time.monotonic()+20
            while run(['systemctl','show','vipi-expiry.service','--property=ActiveState','--value']).strip() not in ('inactive','failed'):
                require(time.monotonic()<deadline,'Existing maintenance did not finish');time.sleep(.3)
            run(['systemctl','stop','vipi-api.service'])
            install_file(BASE/'new.env',ENV_FILE,0o640,group)
            install_file(new/'ops/vipi-api.service',UNIT)
            install_file(BASE/'new.nginx',NGINX)
            run(['nginx','-t']);activate_link(new);run(['systemctl','daemon-reload'])
            run(['systemctl','start','vipi-api.service']);await_ready(48943)
            run(['systemctl','reload','nginx.service'])
            deadline=time.monotonic()+15
            while True:
                status,body,head=fetch('https://api.mambovipi.app/delete-account')
                if status==200 and b'Delete your Vipi account' in body and head.get_all('Referrer-Policy')==['same-origin']: break
                require(time.monotonic()<deadline,'Public browser headers did not adopt');time.sleep(.3)
            require(fetch('https://api.mambovipi.app/health/live')[0]==200,'Public health failed')
            require(fetch('https://api.mambovipi.app/health/ready')[0]==403,'Readiness became public')
            require(fetch('https://api.mambovipi.app/v1/me')[0]==401,'API authentication changed')
            require(fetch('https://api.mambovipi.app/delete-account/style.css')[0]==200,'Public CSS failed')
            run(['systemctl','start','vipi-expiry.timer'])
            receipt['protected_after_apply']=verify_protected(before)
            receipt['state']='active_verified';receipt['finished_at']=datetime.now(UTC).isoformat();save(receipt)
        except BaseException as error:
            receipt['failure_type']=type(error).__name__;receipt['state']='activation_failed';save(receipt)
            # Never undo accepted deletion or restore its data. With no new
            # deletion jobs, the old DB/release are an exact, separate fallback.
            if sql('SELECT count(*) FROM account_deletions',DATABASE)!='0':
                receipt['state']='repair_required_deletion_work_preserved';save(receipt)
                run(['systemctl','start','vipi-expiry.timer']);raise
            run(['systemctl','stop','vipi-api.service','vipi-expiry.timer'])
            install_file(BASE/'old.env',ENV_FILE,0o640,group);install_file(BASE/'old.service',UNIT);install_file(BASE/'old.nginx',NGINX)
            run(['nginx','-t']);activate_link(old);run(['systemctl','daemon-reload']);run(['systemctl','start','vipi-api.service'])
            await_ready(48943);run(['systemctl','reload','nginx.service']);run(['systemctl','start','vipi-expiry.timer'])
            receipt['state']='rolled_back_verified';save(receipt);raise
    print(json.dumps({'state':receipt['state'],'receipt':str(BASE/'receipt.json'),'new_revision':args.revision,'database':DATABASE}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['stage','apply']);parser.add_argument('revision');parser.add_argument('--expected-current',required=True)
    parser.add_argument('--private-config')
    args=parser.parse_args();os.umask(0o077)
    require(args.action!='stage' or args.private_config,'Staging requires a private configuration file')
    main(args)
