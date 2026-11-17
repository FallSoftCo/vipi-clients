import asyncio
import secrets
from uuid import uuid4
import pytest
from sqlalchemy import select
from conftest import NOW
from test_api import identity
from test_global_deletion import client, operation
from test_identity_linking import SECRET
from vipi import global_deletion
from vipi.db import User, VipiTrialEligibility, GlobalDeletionHold
from vipi.deletion import request_deletion
from vipi.identity_authorities import canonical_shared_subject
from vipi.eligibility import eligibility_hash

async def test_global_alias_hold_serializes_with_legacy_reprovision(db, monkeypatch):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('Deterministic actual PostgreSQL commit interleaving')
    target=canonical_shared_subject('user_shared_alice')
    async with client(db) as api:
        profile,_,headers=await identity(api,'alice')
        linked=await api.post('/v1/identity-links/fallsoft',headers=headers,json={'request_id':str(uuid4()),'expected_account_id':profile['id'],'fallsoft_access_token':'shared-alice'})
        assert linked.status_code==200
        async with db.sessions.begin() as session:
            await request_deletion(session,subject=target,account_id=profile['id'],receipt_secret=secrets.token_urlsafe(32),service_secret=SECRET,now=NOW)
        checked=asyncio.Event();resume=asyncio.Event();alias_attempted=asyncio.Event();original=global_deletion.provision_blocked
        async def paused(session,subject,service_secret):
            blocked=await original(session,subject,service_secret)
            if subject=='user_qa_alice' and not blocked:
                checked.set();await asyncio.wait_for(resume.wait(),5)
            return blocked
        monkeypatch.setattr(global_deletion,'provision_blocked',paused)
        original_lock=getattr(global_deletion,'lock_lifecycle_hash',None)
        if original_lock is not None:
            async def observed_alias_lock(session,digest):
                if digest==eligibility_hash('user_qa_alice',SECRET):
                    alias_attempted.set()
                return await original_lock(session,digest)
            monkeypatch.setattr(global_deletion,'lock_lifecycle_hash',observed_alias_lock)
        registration=asyncio.create_task(api.put('/v1/me',headers={'Authorization':'Bearer alice'},json={'username':'race_recreated','display_name':'Synthetic'}))
        await asyncio.wait_for(checked.wait(),5)
        async def perform_global():
            async with db.sessions.begin() as session:
                result=await global_deletion.erase(session,operation(),SECRET,NOW)
                assert result['status']=='complete'
        erasure=asyncio.create_task(perform_global())
        attempted=asyncio.create_task(alias_attempted.wait())
        try:
            # Fixed code reaches the alias-lock attempt and waits for legacy.
            # Vulnerable code commits first. No scheduling delay chooses which.
            completed,_=await asyncio.wait({erasure,attempted},timeout=5,return_when=asyncio.FIRST_COMPLETED)
            assert completed, 'Global erasure reached neither completion nor the retained-alias lock'
        finally:
            resume.set()
            attempted.cancel()
            await asyncio.gather(attempted,return_exceptions=True)
        reply=await asyncio.wait_for(registration,5)
        await asyncio.wait_for(erasure,5)
        async with db.sessions() as session:
            restored=(await session.scalars(select(User).where(User.subject=='user_qa_alice'))).all()
            ledger=(await session.scalars(select(VipiTrialEligibility))).all()
            holds=(await session.scalars(select(GlobalDeletionHold))).all()
        assert reply.status_code in (403,409) and not restored and not ledger, {'registration_status':reply.status_code,'legacy_profiles_after_complete':len(restored),'trial_records_after_complete':len(ledger),'holds':len(holds)}
