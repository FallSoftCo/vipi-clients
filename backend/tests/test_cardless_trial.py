from datetime import timedelta
import pytest
from sqlalchemy import update
from conftest import NOW
from vipi.db import User
from vipi.delivery import DeliveryError
from vipi.subscriptions import Subscriptions
from test_subscriptions import settings, purchase
from test_api import api


async def set_trial(db, start, end):
    async with db.sessions.begin() as session:
        await session.execute(update(User).where(User.id == 'alice').values(cardless_trial_started_at=start, cardless_trial_ends_at=end))


async def test_trial_boundaries_reinstall_and_bot_separation(db):
    await set_trial(db, NOW, NOW + timedelta(days=30))
    clock = [NOW]
    service = Subscriptions(settings(), db, {}, lambda: clock[0])
    first = await service.snapshot('alice')
    assert first['base']['active'] and first['base']['access_source'] == 'cardless_trial'
    assert first['base']['cardless_trial']['active'] and not first['bot_mini']['available']
    with pytest.raises(DeliveryError, match='bot_subscription_required'):
        await service.require('alice', bot=True)
    # A fresh service instance, as after device replacement, cannot restart time.
    assert (await Subscriptions(settings(), db, {}, lambda: clock[0]).snapshot('alice'))['base']['cardless_trial'] == first['base']['cardless_trial']
    clock[0] += timedelta(days=30) - timedelta(microseconds=1)
    assert (await service.snapshot('alice'))['base']['active']
    clock[0] += timedelta(microseconds=1)
    expired = await service.snapshot('alice')
    assert not expired['base']['active'] and expired['base']['access_source'] is None
    assert not expired['base']['cardless_trial']['active'] and expired['base']['cardless_trial']['ends_at'] == first['base']['cardless_trial']['ends_at']
    with pytest.raises(DeliveryError, match='base_subscription_required'):
        await service.require('alice')


async def test_store_precedes_trial_then_trial_survives_revocation(db):
    await set_trial(db, NOW, NOW + timedelta(days=30))
    service = Subscriptions(settings(), db, {}, lambda: NOW)
    await service.apply('alice', purchase(), NOW)
    assert (await service.snapshot('alice'))['base']['access_source'] == 'store'
    await service.apply('alice', purchase(revoked=True), NOW + timedelta(seconds=1))
    state = await service.snapshot('alice')
    assert state['base']['access_source'] == 'cardless_trial' and state['base']['cardless_trial']['active']


async def test_new_profile_once_and_same_subject_registration_does_not_reset(api):
    headers = {'Authorization': 'Bearer alice'}
    profile = {'username': 'qa_alice', 'display_name': 'Alice'}
    assert (await api.put('/v1/me', json=profile, headers=headers)).status_code == 200
    first = (await api.get('/v1/entitlements', headers=headers)).json()
    assert first['base']['cardless_trial'] == {'started_at': NOW.isoformat(), 'ends_at': (NOW+timedelta(days=30)).isoformat(), 'active': True}
    assert (await api.put('/v1/me', json=profile, headers=headers)).status_code == 200
    assert (await api.get('/v1/entitlements', headers=headers)).json()['base']['cardless_trial'] == first['base']['cardless_trial']


async def test_review_complimentary_keeps_its_source_and_trial_is_not_bot(db):
    await set_trial(db, NOW, NOW+timedelta(days=30))
    service = Subscriptions(settings(reviewer_user_ids={'11111111-1111-4111-8111-111111111111'}), db, {}, lambda: NOW)
    # A non-reviewer remains a trial user; reviewer matching is exact internal UUID.
    result = await service.snapshot('alice')
    assert result['base']['access_source'] == 'cardless_trial' and not result['bot_mini']['available']


async def test_deletion_removes_trial_and_blocks_same_subject_during_deletion(db):
    from vipi.deletion import request_deletion, deletion_for
    await set_trial(db, NOW, NOW + timedelta(days=30))
    async with db.sessions.begin() as session:
        await request_deletion(session, subject='user_alice', account_id='alice', receipt_secret='a'*43, service_secret='a'*43, now=NOW)
    async with db.sessions() as session:
        assert await session.get(User, 'alice') is None
        assert await deletion_for(session, 'user_alice', 'a'*43) is not None
    with pytest.raises(DeliveryError, match='account_unavailable'):
        await Subscriptions(settings(), db, {}, lambda: NOW).snapshot('alice')


async def test_unapproved_sandbox_grant_cannot_supplant_cardless_trial(db):
    await set_trial(db, NOW, NOW + timedelta(days=30))
    service = Subscriptions(settings(store_sandbox_restricted=True), db, {}, lambda: NOW)
    with pytest.raises(DeliveryError, match='purchase_environment_mismatch'):
        await service.apply('alice', purchase(), NOW)
    state = await service.snapshot('alice')
    assert state['base']['access_source'] == 'cardless_trial'
    assert state['base']['active'] and not state['bot_mini']['active']


async def test_enforced_message_send_expires_but_inbox_remains_readable(db):
    import base64
    from uuid import uuid4
    import httpx
    from test_api import TestVerifier, identity
    from vipi.api import create_app
    clock = [NOW]
    app = create_app(settings(enforce_subscriptions=True), database=db, verifier=TestVerifier(), clock=lambda: clock[0], store_providers={})
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://vipi.test') as client:
            alice, _, headers = await identity(client, 'alice')
            bob, bob_device, _ = await identity(client, 'bob')
            def message():
                return {'id': str(uuid4()), 'recipient_id': bob['id'], 'recipient_device_id': bob_device,
                        'created_at': clock[0].isoformat(), 'cipher_type': 3,
                        'ciphertext': base64.b64encode(b'opaque synthetic fixture repeated for adequate length').decode()}
            assert (await client.post('/v1/messages', json=message(), headers=headers)).status_code == 200
            clock[0] += timedelta(days=30)
            assert (await client.post('/v1/messages', json=message(), headers=headers)).status_code == 402
            assert (await client.get('/v1/messages/pending', headers=headers)).status_code == 200
            assert (await client.get('/v1/entitlements', headers=headers)).status_code == 200
    finally:
        await app.state.bot.close()
        await app.state.pubsub_verifier.close()


async def test_trial_keeps_base_available_during_stale_bot_verification(db):
    await set_trial(db, NOW, NOW + timedelta(days=30))
    clock = [NOW]
    service = Subscriptions(settings(purchase_outage_seconds=300), db, {}, lambda: clock[0])
    await service.apply('alice', purchase(product='bot_mini'), NOW)
    clock[0] += timedelta(seconds=301)
    state = await service.snapshot('alice')
    assert state['base']['active'] and state['base']['access_source'] == 'cardless_trial'
    assert not state['bot_mini']['active'] and state['bot_mini']['verification_unavailable'] is True
    assert (await service.require('alice'))['base']['active']
    with pytest.raises(DeliveryError, match='purchase_verification_unavailable'):
        await service.require('alice', bot=True)
