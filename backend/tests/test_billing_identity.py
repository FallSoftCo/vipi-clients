"""Current store verification plus durable exact identity binding, no real stores."""
import secrets
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from conftest import NOW
from test_subscriptions import settings, google_document
from vipi.billing_identity import binding_hash, billing_account_id, retain_account
from vipi.db import AccountDeletion, BillingAccountBinding, Entitlement, User
from vipi.deletion import expire_deletion_receipts, request_deletion
from vipi.delivery import DeliveryError
from vipi.eligibility import eligibility_hash
from vipi.global_deletion import erase
from vipi.identity_authorities import canonical_shared_subject
from vipi.store_providers import AppleProvider, GoogleProvider
from vipi.subscriptions import Subscriptions

SUBJECT = canonical_shared_subject('user_paid_owner')
OTHER = canonical_shared_subject('user_paid_other')
SECRET = settings().service_secret


class Store:
    def __init__(self, store, old_id):
        self.store, self.old_id = store, old_id
        self.revoked = False
        self.after_read = None
        self.ack = 0
        self.reads = 0
        self.identifier = old_id if store == 'apple' else billing_account_id(old_id)
        if store == 'google':
            async def response(request):
                if request.method == 'POST':
                    self.ack += 1
                    return httpx.Response(204)
                self.reads += 1
                if self.after_read:
                    action, self.after_read = self.after_read, None
                    await action()
                data = google_document(old_id)
                data['externalAccountIdentifiers']['obfuscatedExternalAccountId'] = self.identifier
                data['lineItems'][0]['expiryTime'] = (NOW + timedelta(days=365)).isoformat()
                if self.revoked: data['subscriptionState'] = 'SUBSCRIPTION_STATE_EXPIRED'
                return httpx.Response(200, json=data)
            self.provider = GoogleProvider(settings(), transport=httpx.MockTransport(response), credentials=SimpleNamespace(valid=True, token='fixture-only'))
        else:
            self.provider = AppleProvider.__new__(AppleProvider)
            self.provider.environment = 'Production'
            async def decode(_):
                return SimpleNamespace(productId='vipi.base.annual', type='Auto-Renewable Subscription',
                    appAccountToken=self.identifier, originalTransactionId='123456',
                    expiresDate=int((NOW+timedelta(days=365)).timestamp()*1000),
                    revocationDate=1 if self.revoked else None, offerDiscountType=None)
            async def status(_):
                self.reads += 1
                if self.after_read:
                    action, self.after_read = self.after_read, None
                    await action()
                return SimpleNamespace(data=[SimpleNamespace(lastTransactions=[SimpleNamespace(
                    originalTransactionId='123456', signedTransactionInfo='current-signed-fixture', status=1)])])
            self.provider.decode = decode
            self.provider.client = SimpleNamespace(get_all_subscription_statuses=status)

    async def close(self):
        if self.store == 'google': await self.provider.close()


def credential(store):
    return 'opaque-purchase-fixture' if store == 'google' else 'signed-purchase-fixture'


async def add(db, subject=SUBJECT):
    identifier = str(uuid4())
    async with db.sessions.begin() as session:
        session.add(User(id=identifier, subject=subject, username='paid_'+identifier[:8], display_name='QA',
            created_at=NOW, cardless_trial_started_at=NOW-timedelta(days=40), cardless_trial_ends_at=NOW-timedelta(days=10)))
    return identifier


async def remove(db, identifier, subject=SUBJECT):
    async with db.sessions.begin() as session:
        await request_deletion(session, subject=subject, account_id=identifier, receipt_secret=secrets.token_urlsafe(32),
            service_secret=SECRET, now=NOW)


@pytest.mark.parametrize('store', ['apple', 'google'])
@pytest.mark.parametrize('paid_before_delete', [False, True])
async def test_same_shared_identity_restores_after_receipt_expiry_without_retaining_grant(db, store, paid_before_delete):
    old = await add(db)
    fixture = Store(store, old)
    service = Subscriptions(settings(), db, {store:fixture.provider}, lambda:NOW)
    try:
        if paid_before_delete:
            await service.sync(old, store, credential(store))
        else:
            # Historical store approval could precede verification in an old
            # paid client. Current free accounts never issue these bindings.
            async with db.sessions.begin() as session:
                await retain_account(session, subject=SUBJECT, user_id=old, service_secret=SECRET)
        await remove(db, old)
        async with db.sessions.begin() as session:
            await expire_deletion_receipts(session, NOW+timedelta(days=8))
        async with db.sessions() as session:
            assert await session.get(User, old) is None
            assert await session.scalar(select(func.count()).select_from(Entitlement)) == 0
            assert await session.scalar(select(func.count()).select_from(AccountDeletion)) == 0
            rows = (await session.scalars(select(BillingAccountBinding))).all()
            assert len(rows) == 2
            assert all(r.owner_hash == eligibility_hash(SUBJECT, SECRET) for r in rows)
            assert set(BillingAccountBinding.__table__.columns.keys()) == {'store', 'binding_hash', 'owner_hash'}
            assert all(old not in r.binding_hash and SUBJECT not in r.owner_hash for r in rows)
        new = await add(db)
        # Equal display names never establish ownership of the old purchase.
        other = await add(db, OTHER)
        with pytest.raises(DeliveryError, match='purchase_account_mismatch'):
            await service.sync(other, store, credential(store))
        result = await service.sync(new, store, credential(store), expected_subject=SUBJECT)
        assert result['base']['access_source'] == 'store'
        assert result['app_account_token'] == new and result['billing_account_id'] == billing_account_id(new)
        async with db.sessions() as session:
            assert (await session.scalars(select(Entitlement))).one().user_id == new
        async with db.sessions.begin() as session:
            (await session.scalars(select(Entitlement).where(Entitlement.user_id == new))).one().next_attempt_at = NOW
        assert await service.reconcile_one()
        fixture.revoked = True
        await service.sync(new, store, credential(store))
        assert not (await service.snapshot(new))['base']['active']
    finally: await fixture.close()


@pytest.mark.parametrize('store', ['apple', 'google'])
async def test_signed_or_authoritative_unknown_missing_ownership_never_matches(db, store):
    old = await add(db); await remove(db, old); new = await add(db)
    fixture = Store(store, old)
    service = Subscriptions(settings(), db, {store:fixture.provider}, lambda:NOW)
    try:
        fixture.identifier = str(uuid4()) if store == 'apple' else 'different-account'
        with pytest.raises(DeliveryError, match='purchase_account_mismatch'):
            await service.sync(new, store, credential(store))
        fixture.identifier = None
        with pytest.raises(DeliveryError): await service.sync(new, store, credential(store))
        async with db.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Entitlement)) == 0
        assert fixture.ack == 0
    finally: await fixture.close()


@pytest.mark.parametrize('store', ['apple', 'google'])
@pytest.mark.parametrize('crossing', ['link', 'delete', 'global'])
async def test_network_crossing_identity_transition_cannot_grant_or_acknowledge(db, store, crossing):
    identifier = await add(db)
    fixture = Store(store, identifier)
    service = Subscriptions(settings(), db, {store:fixture.provider}, lambda:NOW)
    async def transition():
        if crossing == 'delete': await remove(db, identifier)
        elif crossing == 'link':
            async with db.sessions.begin() as session:
                # Simulate a committed link during the provider read. Actual
                # device/dual-proof linking is exercised separately below.
                (await session.get(User, identifier)).subject = OTHER
        else:
            from test_global_deletion import operation
            async with db.sessions.begin() as session:
                await erase(session, operation(subject='user_paid_owner'), SECRET, NOW)
    fixture.after_read = transition
    try:
        with pytest.raises(DeliveryError, match='account_unavailable'):
            await service.sync(identifier, store, credential(store), expected_subject=SUBJECT)
        async with db.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Entitlement)) == 0
            if crossing == 'global': assert await session.scalar(select(func.count()).select_from(BillingAccountBinding)) == 0
        assert fixture.ack == 0
    finally: await fixture.close()


async def test_exact_store_domain_hash_ownership_cannot_be_overwritten(db):
    identifier = await add(db)
    async with db.sessions.begin() as session:
        await retain_account(session, subject=SUBJECT, user_id=identifier, service_secret=SECRET)
    with pytest.raises(DeliveryError, match='purchase_account_mismatch'):
        async with db.sessions.begin() as session:
            await retain_account(session, subject=OTHER, user_id=identifier, service_secret=SECRET)
    assert binding_hash('apple', identifier.upper(), SECRET) == binding_hash('apple', identifier, SECRET)
    assert binding_hash('apple', identifier, SECRET) != binding_hash('google', identifier, SECRET)
    assert binding_hash('google', identifier.upper(), SECRET) != binding_hash('google', identifier, SECRET)


async def test_explicit_link_rekeys_historical_binding_and_global_erases_alias_and_new_seed(db):
    from test_api import identity
    from test_identity_linking import client, SECRET as link_secret
    from test_global_deletion import operation
    async with client(db) as api:
        account, _, headers = await identity(api, 'alice')
        async with db.sessions.begin() as session:
            await retain_account(session, subject='user_qa_alice', user_id=account['id'], service_secret=link_secret)
        linked = await api.post('/v1/identity-links/fallsoft', headers=headers, json={
            'request_id':str(uuid4()), 'expected_account_id':account['id'], 'fallsoft_access_token':'shared-alice'})
        assert linked.status_code == 200, linked.text
        target = canonical_shared_subject('user_shared_alice')
        async with db.sessions() as session:
            rows = (await session.scalars(select(BillingAccountBinding))).all()
            assert len(rows) == 2 and {r.owner_hash for r in rows} == {eligibility_hash(target, link_secret)}
        async with db.sessions.begin() as session:
            result = await erase(session, operation(), link_secret, NOW)
            assert result['status'] == 'complete'
        async with db.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(BillingAccountBinding)) == 0


async def test_stale_authenticated_subject_is_rejected_before_store_read(db):
    identifier = await add(db)
    fixture = Store('google', identifier)
    service = Subscriptions(settings(), db, {'google':fixture.provider}, lambda:NOW)
    try:
        with pytest.raises(DeliveryError, match='account_unavailable'):
            await service.sync(identifier, 'google', credential('google'), expected_subject=OTHER)
        assert fixture.reads == fixture.ack == 0
    finally: await fixture.close()


@pytest.mark.parametrize('cause', ['lost-lease', 'newer-observation'])
async def test_worker_noop_cannot_acknowledge_or_replace_fresher_state(db, cause):
    from test_subscriptions import purchase
    identifier = await add(db)
    value = purchase(environment='Production')
    class Provider:
        ack = 0
        async def verify(self, *args, **kwargs):
            async with db.sessions.begin() as session:
                row = (await session.scalars(select(Entitlement).where(Entitlement.user_id == identifier))).one()
                if cause == 'lost-lease': row.lease_token = 'replacement-owner'
                else: row.verified_at = NOW+timedelta(seconds=1); row.revoked = True
            return value
        async def acknowledge(self, _): self.ack += 1
    provider = Provider()
    service = Subscriptions(settings(), db, {'google':provider}, lambda:NOW)
    await service.apply(identifier, value, NOW)
    async with db.sessions.begin() as session:
        row = (await session.scalars(select(Entitlement).where(Entitlement.user_id == identifier))).one()
        row.next_attempt_at = NOW
    assert await service.reconcile_one()
    assert provider.ack == 0
    async with db.sessions() as session:
        row = (await session.scalars(select(Entitlement).where(Entitlement.user_id == identifier))).one()
        if cause == 'lost-lease': assert row.lease_token == 'replacement-owner'
        else: assert row.revoked


async def test_free_api_rejoin_keeps_purchase_route_retired_and_never_reaches_store(db):
    from vipi.api import create_app
    from vipi.auth import Principal
    current = [NOW]
    class Verifier:
        async def verify(self, token):
            return Principal(SUBJECT, 'fixture-session', int((NOW if token == 'old' else current[0]).timestamp()))
    providers = {}
    app = create_app(settings(account_deletion_enabled=True), database=db, verifier=Verifier(),
        clock=lambda:current[0], store_providers=providers)
    old_headers = {'Authorization':'Bearer old'}
    fresh_headers = {'Authorization':'Bearer fresh'}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://vipi.test') as api:
        old = (await api.put('/v1/me', headers=old_headers, json={'username':'paid_api','display_name':'QA'})).json()['id']
        fixture = Store('google', old); providers['google'] = fixture.provider
        try:
            # Only the historical reconciliation worker can inspect old store
            # receipts; current API purchase/restore entry points stay retired.
            historical = Subscriptions(settings(), db, providers, lambda:NOW)
            await historical.sync(old, 'google', credential('google'))
            current[0] += timedelta(seconds=1)
            deleted = await api.request('DELETE','/v1/me',headers=old_headers,json={
                'account_id':old,'receipt_secret':secrets.token_urlsafe(32)})
            assert deleted.status_code == 202, deleted.text
            current[0] += timedelta(days=8)
            async with db.sessions.begin() as session: await expire_deletion_receipts(session,current[0])
            rejoined = await api.put('/v1/me',headers=fresh_headers,json={'username':'paid_rejoined','display_name':'QA'})
            assert rejoined.status_code == 200,rejoined.text
            new = rejoined.json()['id'];assert new != old
            before = fixture.reads
            stale = await api.post('/v1/purchases/google',headers=old_headers,json={'purchase_token':credential('google')})
            assert stale.status_code == 410 and fixture.reads == before
            restored = await api.post('/v1/purchases/google',headers=fresh_headers,json={'purchase_token':credential('google')})
            assert restored.status_code == 410 and fixture.reads == before
            access = await api.get('/v1/entitlements', headers=fresh_headers)
            assert access.json()['base']['access_source'] == 'free'
        finally: await fixture.close()


async def test_current_uuid_collision_cannot_override_retained_other_identity_owner(db):
    from vipi.billing_identity import matches_account
    identifier = await add(db)
    async with db.sessions.begin() as session:
        await retain_account(session, subject=SUBJECT, user_id=identifier, service_secret=SECRET)
    # Even a malformed/restored profile reusing a historical UUID must not take
    # the original identity's billing ownership through the current-id shortcut.
    async with db.sessions() as session:
        assert not await matches_account(session, subject=OTHER, user_id=identifier, store='apple', identifier=identifier, service_secret=SECRET)
        assert not await matches_account(session, subject=OTHER, user_id=identifier, store='google', identifier=billing_account_id(identifier), service_secret=SECRET)
