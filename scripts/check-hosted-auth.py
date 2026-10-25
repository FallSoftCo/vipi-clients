#!/usr/bin/env python3
"""Retained real AuthKit browser probe, restricted to tagged Vipi staging QA."""
import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sys
from urllib.parse import urlencode
from uuid import uuid4
import httpx

ROOT=Path('/aosp/development/vipi')
sys.path.insert(0,str(ROOT/'backend'))
from vipi.auth import WorkOSVerifier
from vipi.config import Settings

CLIENT='client_01M5S2CDSQ8F7FEX26G3CY9VS1'
PRIVATE=Path('/home/aosp/.local/state/vipi/workos-isolated')


async def main(args):
    assert socket.gethostname()=='ozzz-aosp'
    private=PRIVATE/f'hosted-auth-{args.revision}.json'
    receipt=ROOT/f'artifacts/hosted-auth-{args.revision}.json'
    key=(PRIVATE/'api-key').read_text().strip(); assert key.startswith('sk_test_')
    async with httpx.AsyncClient(base_url='https://api.workos.com',headers={'Authorization':'Bearer '+key},timeout=20,follow_redirects=False) as api:
        if args.action=='prepare':
            assert not private.exists() and not receipt.exists()
            tag='vipi-auth-'+uuid4().hex
            value={'tag':tag,'email':tag+'@fallsoft.co','password':secrets.token_urlsafe(32)+'aA1!'}
            private.write_text(json.dumps(value));private.chmod(0o600)
            created=await api.post('/user_management/users',json={'email':value['email'],'email_verified':True,'password':value['password'],'metadata':{'vipi_qa_run':tag}})
            assert created.status_code in (200,201),'fixture creation failed'
            value['subject']=created.json()['id']
            report={'client_id':CLIENT,'real_provider':True,'stages':[],'cleanup_confirmed':False}
        else:
            value=json.loads(private.read_text());report=json.loads(receipt.read_text())
        if args.action=='exchange':
            callback=json.loads((PRIVATE/f'hosted-callback-{args.revision}.json').read_text())
            assert secrets.compare_digest(value['state'],callback['state'])
            result=await api.post('/user_management/authenticate',json={'client_id':CLIENT,'client_secret':key,
                'grant_type':'authorization_code','code':callback['code'],'code_verifier':value['verifier']})
            assert result.status_code==200,'code exchange failed'
            tokens=result.json();assert tokens['user']['id']==value['subject']
            verifier=WorkOSVerifier(Settings(database_url='sqlite+aiosqlite://',workos_client_id=CLIENT,workos_issuer='https://api.workos.com',service_secret=secrets.token_urlsafe(32)))
            try: principal=await verifier.verify(tokens['access_token'])
            finally: await verifier.close()
            assert principal.subject==value['subject']
            if report['stages']:
                assert principal.authenticated_at>report['stages'][-1]['auth_time'],'fresh authentication did not advance'
            report['stages'].append({'real_jwt_verified':True,'auth_time':principal.authenticated_at,'pkce_exchange':True})
            # Access/refresh tokens are not persisted or printed by this probe.
            (PRIVATE/f'hosted-callback-{args.revision}.json').unlink()
        if args.action=='cleanup':
            users=await api.get('/user_management/users',params={'email':value['email'],'limit':10})
            assert users.status_code==200
            for user in users.json().get('data',[]):
                assert user['email']==value['email'] and user.get('metadata',{}).get('vipi_qa_run')==value['tag']
                removed=await api.delete('/user_management/users/'+user['id'])
                assert removed.status_code in (200,204,404)
            checked=await api.get('/user_management/users',params={'email':value['email'],'limit':1})
            report['cleanup_confirmed']=checked.status_code==200 and checked.json().get('data')==[]
            assert report['cleanup_confirmed'];private.unlink()
            report['passed']=len(report['stages'])==2
        else:
            value['state']=secrets.token_urlsafe(32);value['verifier']=secrets.token_urlsafe(48)
            challenge=base64.urlsafe_b64encode(hashlib.sha256(value['verifier'].encode()).digest()).rstrip(b'=').decode()
            value['url']='https://api.workos.com/user_management/authorize?'+urlencode({'client_id':CLIENT,'provider':'authkit',
                'redirect_uri':'https://api.mambovipi.app/delete-account/callback','response_type':'code','max_age':'0','screen_hint':'sign-in',
                'state':value['state'],'code_challenge':challenge,'code_challenge_method':'S256'})
            private.write_text(json.dumps(value));private.chmod(0o600)
        receipt.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'action':args.action,'receipt':str(receipt),'completed_stages':len(report['stages']),'cleanup_confirmed':report['cleanup_confirmed']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','exchange','cleanup']);parser.add_argument('revision')
    args=parser.parse_args();assert args.revision.isdigit() and len(args.revision)==3
    os.umask(0o077);asyncio.run(main(args))
