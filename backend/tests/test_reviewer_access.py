"""Configured complimentary access; no live reviewers or provider calls."""
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from conftest import NOW
from test_subscriptions import settings,purchase
from test_bot import response
from vipi.auth import Principal,AuthenticationError
from vipi.api import create_app
from vipi.bot import BotGateway
from vipi.db import User,Entitlement
from vipi.delivery import DeliveryError
from vipi.subscriptions import Subscriptions

REVIEW='11111111-1111-4111-8111-111111111111'
OTHER='22222222-2222-4222-8222-222222222222'

@pytest.fixture
async def reviewer_db(db):
    async with db.sessions.begin() as s:
        for uid,name in [(REVIEW,'reviewer'),(OTHER,'ordinary')]:
            s.add(User(id=uid,subject='subject_'+name,username=name,display_name=name,created_at=NOW))
    return db


def test_allowlist_is_explicit_canonical_internal_ids_only():
    assert settings().reviewer_user_ids==frozenset()
    for value in ['*','subject_reviewer','reviewer@example.test','11111111111141118111111111111111','00000000-0000-0000-0000-000000000000']:
        with pytest.raises(ValueError):settings(reviewer_user_ids={value})
    with pytest.raises(ValueError):settings(reviewer_user_ids={str(uuid4()) for _ in range(33)})


async def test_exact_authenticated_user_only_and_no_fabricated_purchase(reviewer_db):
    options=settings(reviewer_user_ids={REVIEW},enforce_subscriptions=True)
    class Verifier:
        async def verify(self,token):
            if token not in ['reviewer','ordinary']:raise AuthenticationError('invalid')
            return Principal('subject_'+token,'session_'+token,int(NOW.timestamp()))
    app=create_app(options,database=reviewer_db,verifier=Verifier(),store_providers={})
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as client:
            assert (await client.get('/v1/entitlements')).status_code==401
            assert (await client.get('/v1/entitlements',headers={'Authorization':'Bearer '+REVIEW})).status_code==401
            ordinary=await client.get('/v1/entitlements?user_id='+REVIEW,headers={'Authorization':'Bearer ordinary'})
            assert not ordinary.json()['base']['active']
            reviewed=await client.get('/v1/entitlements',headers={'Authorization':'Bearer reviewer'})
            assert reviewed.status_code==200
            for plan in ['base','bot_mini']:
                access=reviewed.json()[plan]
                assert access['active'] and access['review_access'] and access['access_source']=='review_complimentary'
                assert access['expires_at'] is None and access['trial_ends_at'] is None
            assert reviewed.json()['bot_mini']['available']
            assert reviewed.json()['purchases_ready']=={'apple':False,'google':False}
        async with reviewer_db.sessions() as s:assert not (await s.execute(select(Entitlement))).scalars().all()
    finally:
        await app.state.bot.close();await app.state.pubsub_verifier.close()


async def test_revocation_and_removal_preserve_store_records(reviewer_db):
    grant=Subscriptions(settings(reviewer_user_ids={REVIEW}),reviewer_db,{},lambda:NOW)
    revoked=purchase(revoked=True)
    await grant.apply(REVIEW,revoked,NOW)
    assert (await grant.require(REVIEW,bot=True))['base']['review_access']
    ordinary=Subscriptions(settings(),reviewer_db,{},lambda:NOW)
    with pytest.raises(DeliveryError,match='base_subscription_required'):await ordinary.require(REVIEW,bot=True)
    async with reviewer_db.sessions() as s:
        rows=(await s.execute(select(Entitlement))).scalars().all()
        assert len(rows)==1 and rows[0].revoked and rows[0].transaction_id==revoked.transaction_id
    await ordinary.apply(OTHER,purchase(transaction_id='ordinary'),NOW)
    assert (await ordinary.require(OTHER))['base']['active']
    await ordinary.apply(OTHER,purchase(transaction_id='ordinary',revoked=True),NOW)
    with pytest.raises(DeliveryError,match='base_subscription_required'):await ordinary.require(OTHER)


@pytest.mark.parametrize('state',['suspended','deleted','missing'])
async def test_reviewer_payment_bypass_never_bypasses_account_safety(reviewer_db,state):
    if state!='missing':
        async with reviewer_db.sessions.begin() as s:setattr(await s.get(User,REVIEW),state,True)
    uid=str(uuid4()) if state=='missing' else REVIEW
    service=Subscriptions(settings(reviewer_user_ids={uid}),reviewer_db,{},lambda:NOW)
    with pytest.raises(DeliveryError,match='account_unavailable'):await service.require(uid,bot=True)


async def test_bot_same_provider_consent_context_quota_and_spend_paths(reviewer_db):
    calls=[]
    async def handler(request):calls.append(request);return response()
    async def make(**kw):
        options=settings(reviewer_user_ids={REVIEW},**kw)
        return BotGateway(options,reviewer_db,Subscriptions(options,reviewer_db,{},lambda:NOW),lambda:NOW,transport=httpx.MockTransport(handler))
    missing=await make()
    try:
        assert not (await missing.allowance(REVIEW))['service_ready']
        with pytest.raises(DeliveryError,match='bot_unavailable'):await missing.reply(REVIEW,str(uuid4()),[{'role':'user','content':'Hello'}],'deepseek-v1')
    finally:await missing.close()
    bot=await make(deepseek_api_key='synthetic-only',bot_monthly_replies=1)
    try:
        for messages,consent,error in [([{'role':'user','content':'Hi'}],'wrong','bot_consent_required'),([{'role':'user','content':'x'*8193}],'deepseek-v1','bot_context_too_large')]:
            with pytest.raises(DeliveryError,match=error):await bot.reply(REVIEW,str(uuid4()),messages,consent)
        with pytest.raises(DeliveryError,match='base_subscription_required'):await bot.reply(OTHER,str(uuid4()),[{'role':'user','content':'Hi'}],'deepseek-v1')
        assert not calls
        result=await bot.reply(REVIEW,str(uuid4()),[{'role':'user','content':'Hi'}],'deepseek-v1')
        assert result['allowance']['remaining_replies']==0 and len(calls)==1
        with pytest.raises(DeliveryError,match='monthly_allowance_reached'):await bot.reply(REVIEW,str(uuid4()),[{'role':'user','content':'Hi'}],'deepseek-v1')
        assert len(calls)==1
    finally:await bot.close()
    capped=await make(deepseek_api_key='synthetic-only',bot_global_monthly_budget_nano_usd=1)
    try:
        with pytest.raises(DeliveryError,match='bot_temporarily_unavailable'):await capped.reply(REVIEW,str(uuid4()),[{'role':'user','content':'Hi'}],'deepseek-v1')
        assert len(calls)==1
    finally:await capped.close()
