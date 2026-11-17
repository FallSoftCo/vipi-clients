from types import SimpleNamespace
from uuid import uuid4
import httpx
import pytest
from sqlalchemy import select
from conftest import NOW
from test_subscriptions import purchase, settings
from test_deployment_config import configuration
from vipi.db import Entitlement, User
from vipi.delivery import DeliveryError
from vipi.store_notifications import retain
from vipi.store_providers import AccountScopedAppleProvider, GoogleProvider
from vipi.subscriptions import Subscriptions, billing_account_id


def production(**changes):
    return configuration(environment='production', database_url='postgresql+asyncpg://fixture.invalid/test', enforce_subscriptions=True, **changes)


async def test_google_test_grant_restricted_and_removal_masks(db):
    tester, other = str(uuid4()), str(uuid4())
    async with db.sessions.begin() as s:
        for i, user in enumerate((tester, other)):
            s.add(User(id=user, subject='sandbox-test-'+str(i), username='sandbox'+str(i), display_name='test', created_at=NOW))
    opts=production(store_sandbox_user_ids=frozenset({tester}))
    data={'externalAccountIdentifiers': {'obfuscatedExternalAccountId': billing_account_id(tester)}, 'testPurchase': {},
          'subscriptionState':'SUBSCRIPTION_STATE_ACTIVE','acknowledgementState':'ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED',
          'lineItems':[{'productId':'vipi_base','expiryTime':'2027-01-24T12:00:00Z','offerDetails':{'basePlanId':'annual'}}]}
    provider=GoogleProvider(opts, credentials=SimpleNamespace(valid=True, token='fixture-only'),transport=httpx.MockTransport(lambda _:httpx.Response(200,json=data)))
    service=Subscriptions(opts,db,{'google':provider},lambda:NOW)
    try:
        assert (await service.sync(tester,'google','fixture-token'))['base']['active']
        with pytest.raises(DeliveryError,match='purchase_account_mismatch'):
            await service.sync(other,'google','fixture-token')
        data['externalAccountIdentifiers']['obfuscatedExternalAccountId']=billing_account_id(other)
        with pytest.raises(DeliveryError,match='purchase_environment_mismatch'):
            await service.sync(other,'google','different-token')
        service.settings=production()
        assert not (await service.snapshot(tester))['base']['active']
        with pytest.raises(DeliveryError,match='purchase_environment_mismatch'):
            await provider.verify_for_environment('fixture-token',other,'Production')
    finally: await provider.close()


class Stub:
    def __init__(self, result): self.result,self.calls=result,0
    async def verify(self, credential,user,*,initial):
        self.calls+=1
        if isinstance(self.result,Exception):raise self.result
        return self.result


async def test_apple_fallback_only_verified_mismatch_and_allowlisted():
    tester=str(uuid4());p=AccountScopedAppleProvider.__new__(AccountScopedAppleProvider);p.settings=production(store_sandbox_user_ids=frozenset({tester}))
    p.production=Stub(DeliveryError('purchase_environment_mismatch',400));p.sandbox=Stub(purchase(store='apple',environment='Sandbox'))
    assert (await p.verify('fixture',tester,initial=True)).environment=='Sandbox'
    with pytest.raises(DeliveryError,match='purchase_environment_mismatch'):await p.verify('fixture',str(uuid4()),initial=True)
    p.production=Stub(DeliveryError('purchase_invalid',400));p.sandbox.calls=0
    with pytest.raises(DeliveryError,match='purchase_invalid'):await p.verify('forged',tester,initial=True)
    assert p.sandbox.calls==0
    p.production=Stub(DeliveryError('purchase_verification_unavailable',503))
    with pytest.raises(DeliveryError,match='purchase_verification_unavailable'):await p.verify('outage',tester,initial=True)
    assert p.sandbox.calls==0


async def test_environment_collision_and_notification_scope(db):
    service=Subscriptions(settings(),db,{},lambda:NOW)
    await service.apply('alice',purchase(store='apple',transaction_id='same',environment='Production'),NOW)
    await service.apply('bob',purchase(store='apple',transaction_id='same',environment='Sandbox'),NOW)
    await retain(db,store='apple',event_id='S_00000000-0000-4000-8000-000000000000',digest='a'*64,transaction_id='same',now=NOW,environment='Sandbox')
    async with db.sessions() as s:
        rows=(await s.execute(select(Entitlement))).scalars().all()
        assert {(r.environment,r.refresh_generation) for r in rows}=={('Production',0),('Sandbox',1)}


async def test_sandbox_refresh_uses_stored_environment_and_stops_after_allowlist_removed(db):
    tester=str(uuid4())
    async with db.sessions.begin() as s:
        s.add(User(id=tester,subject='test-refresh',username='refresh',display_name='Test',created_at=NOW))
    class Refresh:
        def __init__(self): self.calls=[]
        async def verify_for_environment(self, token, user, environment):
            self.calls.append((user,environment))
            return purchase(store='apple',transaction_id='refresh-id',environment='Sandbox')
        async def acknowledge(self, value): pass
    provider=Refresh();opts=production(store_sandbox_user_ids=frozenset({tester}))
    service=Subscriptions(opts,db,{'apple':provider},lambda:NOW)
    await service.apply(tester,purchase(store='apple',transaction_id='refresh-id',environment='Sandbox'),NOW)
    await retain(db,store='apple',event_id='S_00000000-0000-4000-8000-000000000000',digest='b'*64,transaction_id='refresh-id',environment='Sandbox',now=NOW)
    assert await service.reconcile_one()
    assert provider.calls==[(tester,'Sandbox')]
    service.settings=production()
    assert not (await service.snapshot(tester))['base']['active']
    await retain(db,store='apple',event_id='S_00000000-0000-4000-8000-000000000001',digest='c'*64,transaction_id='refresh-id',environment='Sandbox',now=NOW)
    assert await service.reconcile_one()
    assert provider.calls==[(tester,'Sandbox')]


async def test_google_event_collision_only_schedules_reverification(db):
    service=Subscriptions(settings(),db,{},lambda:NOW)
    await service.apply('alice',purchase(store='google',transaction_id='same',environment='Production'),NOW)
    await service.apply('bob',purchase(store='google',transaction_id='same',environment='Sandbox'),NOW)
    await retain(db,store='google',event_id='g1',digest='d'*64,transaction_id='same',now=NOW)
    async with db.sessions() as s:
        rows=(await s.execute(select(Entitlement))).scalars().all()
        assert {(r.environment,r.refresh_generation) for r in rows}=={('Production',1),('Sandbox',1)}


async def test_apple_sandbox_verified_transaction_must_match_authenticated_user(db):
    from vipi.store_providers import AppleProvider
    tester, other = str(uuid4()), str(uuid4())
    async with db.sessions.begin() as s:
        s.add(User(id=tester,subject='apple-sandbox',username='applesandbox',display_name='Test',created_at=NOW))
    transaction=SimpleNamespace(productId='vipi.base.annual',type='Auto-Renewable Subscription',appAccountToken=tester,
        originalTransactionId='12345',expiresDate=1800000000000,revocationDate=None,offerDiscountType='FREE_TRIAL')
    apple=AppleProvider.__new__(AppleProvider);apple.environment='Sandbox'
    async def decode(value): return transaction
    async def status(value): return SimpleNamespace(data=[SimpleNamespace(lastTransactions=[SimpleNamespace(originalTransactionId='12345',signedTransactionInfo='fixture',status=1)])])
    apple.decode=decode;apple.client=SimpleNamespace(get_all_subscription_statuses=status)
    wrapper=AccountScopedAppleProvider.__new__(AccountScopedAppleProvider)
    wrapper.settings=production(store_sandbox_user_ids=frozenset({tester,other}))
    wrapper.production=Stub(DeliveryError('purchase_environment_mismatch',400));wrapper.sandbox=apple
    service=Subscriptions(wrapper.settings,db,{'apple':wrapper},lambda:NOW)
    assert (await service.sync(tester,'apple','verified-fixture'))['base']['active']
    with pytest.raises(DeliveryError,match='purchase_account_mismatch'):
        await wrapper.verify('verified-fixture',other,initial=True)


async def test_apple_notification_fallback_checks_separate_sandbox_verifier():
    class Notice:
        def __init__(self, outcome): self.outcome,self.calls=outcome,0
        async def notification(self, signed):
            self.calls+=1
            if isinstance(self.outcome,Exception):raise self.outcome
            return self.outcome
    p=AccountScopedAppleProvider.__new__(AccountScopedAppleProvider)
    p.production=Notice(DeliveryError('notification_app_identifier_mismatch',400))
    p.sandbox=Notice(('00000000-0000-4000-8000-000000000000','123','d'*64))
    assert (await p.notification('signed-fixture'))[-1]=='Sandbox'
    p.production=Notice(DeliveryError('notification_verification_unavailable',503));p.sandbox.calls=0
    with pytest.raises(DeliveryError,match='notification_verification_unavailable'):
        await p.notification('outage')
    assert p.sandbox.calls==0


async def test_unknown_verified_row_is_masked_and_legacy_tombstone_cannot_revive(db):
    from datetime import timedelta
    tester=str(uuid4())
    async with db.sessions.begin() as s:
        s.add(User(id=tester,subject='unknown-test',username='unknown',display_name='Test',created_at=NOW))
        await s.flush()
        s.add(Entitlement(id=str(uuid4()),user_id=tester,product='base',store='apple',transaction_id='unknown',
            environment='Unknown',expires_at=NOW+timedelta(days=1),verified_at=NOW,revoked=False,superseded=False))
    service=Subscriptions(production(store_sandbox_user_ids=frozenset({tester})),db,{},lambda:NOW)
    assert not (await service.snapshot(tester))['base']['active']
    with pytest.raises(DeliveryError,match='purchase_environment_mismatch'):
        await service.apply(tester,purchase(store='apple',transaction_id='unknown',environment='Production'),NOW)


async def test_old_apple_event_id_replay_only_schedules_existing_grant(db):
    from vipi.db import BillingNotification
    service=Subscriptions(settings(),db,{},lambda:NOW)
    await service.apply('alice',purchase(store='apple',transaction_id='old-event',environment='Production'),NOW)
    event='00000000-0000-4000-8000-000000000000'
    async with db.sessions.begin() as s:
        s.add(BillingNotification(store='apple',id=event,fingerprint='a'*64,created_at=NOW))
    for _ in range(2):
        await retain(db,store='apple',event_id='P_'+event,digest='a'*64,transaction_id='old-event',environment='Production',now=NOW)
    async with db.sessions() as s:
        rows=(await s.execute(select(Entitlement))).scalars().all()
        assert len(rows)==1 and rows[0].refresh_generation==1


async def test_restricted_staging_google_test_grants_only_scoped_account_and_empty_set_fails_closed(db):
    tester, other = str(uuid4()), str(uuid4())
    async with db.sessions.begin() as s:
        for i, user in enumerate((tester, other)):
            s.add(User(id=user,subject='stage-test-'+str(i),username='stage'+str(i),display_name='Test',created_at=NOW))
    def stage(ids):
        return configuration(environment='staging', database_url='postgresql+asyncpg://fixture.invalid/test',
            store_sandbox_restricted=True, store_sandbox_user_ids=frozenset(ids))
    options=stage([tester]);data={'externalAccountIdentifiers':{'obfuscatedExternalAccountId':billing_account_id(tester)},
        'testPurchase':{},'subscriptionState':'SUBSCRIPTION_STATE_ACTIVE','acknowledgementState':'ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED',
        'lineItems':[{'productId':'vipi_base','expiryTime':'2027-01-24T12:00:00Z','offerDetails':{'basePlanId':'annual'}}]}
    provider=GoogleProvider(options,credentials=SimpleNamespace(valid=True,token='fixture-only'),transport=httpx.MockTransport(lambda _:httpx.Response(200,json=data)))
    service=Subscriptions(options,db,{'google':provider},lambda:NOW)
    try:
        assert (await service.sync(tester,'google','staging-token'))['base']['active']
        data['externalAccountIdentifiers']['obfuscatedExternalAccountId']=billing_account_id(other)
        with pytest.raises(DeliveryError,match='purchase_environment_mismatch'):
            await service.sync(other,'google','other-token')
        service.settings=stage([])
        assert not (await service.snapshot(tester))['base']['active']
        with pytest.raises(DeliveryError,match='purchase_environment_mismatch'):
            await service.apply(tester,purchase(environment='Sandbox'),NOW)
    finally:await provider.close()


def test_restricted_staging_uses_dual_apple_verifier_even_with_empty_allowlist(monkeypatch):
    import vipi.store_providers as module
    monkeypatch.setattr(module,'AccountScopedAppleProvider',lambda config:'restricted-verifier')
    monkeypatch.setattr(module,'AppleProvider',lambda config:'legacy-verifier')
    from pathlib import Path
    for restricted, expected in [(True,'restricted-verifier'),(False,'legacy-verifier')]:
        config=configuration(environment='staging',database_url='postgresql+asyncpg://fixture.invalid/test',
            apple_environment='Sandbox',apple_app_id=123,apple_key_id='fixture',apple_issuer_id='fixture',
            apple_private_key_path='/fixture/key',apple_root_certificate_paths=('/fixture/root',),
            store_sandbox_restricted=restricted)
        assert module.providers_for(config)['apple']==expected
