"""HTTP regressions for account-specific testing access and device-safe Bot sends.

Synthetic identities only. The provider is a local MockTransport; denied requests
must not reserve quota, contact the provider, or fabricate store entitlements.
"""
from contextlib import asynccontextmanager
from datetime import timedelta
import secrets
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from conftest import NOW
from test_bot import response
from test_subscriptions import settings
from vipi.api import create_app
from vipi.auth import AuthenticationError, Principal
from vipi.db import Device, Entitlement, Reservation, User
from vipi.identity_authorities import FALLSOFT_VIPI, LEGACY_VIPI

OWNER = '31111111-1111-4111-8111-111111111111'
PINNED = '32222222-2222-4222-8222-222222222222'
LEGACY = '33333333-3333-4333-8333-333333333333'
SUBJECTS = {
    'owner': 'fallsoft-vipi-production:user_actual_owned_fixture',
    'pinned': 'fallsoft-vipi-production:user_previously_pinned_fixture',
    'legacy': 'user_actual_owned_fixture',
}
IDS = {'owner': OWNER, 'pinned': PINNED, 'legacy': LEGACY}


class Verifier:
    async def verify(self, token):
        who = token.removesuffix('_old')
        if who not in SUBJECTS:
            raise AuthenticationError('invalid')
        auth_time = NOW - timedelta(hours=2) if token.endswith('_old') else NOW
        authority = LEGACY_VIPI.id if who == 'legacy' else FALLSOFT_VIPI.id
        return Principal(SUBJECTS[who], 'synthetic_session', int(auth_time.timestamp()), authority)


@pytest.fixture
async def owned_accounts(db):
    async with db.sessions.begin() as session:
        for who, uid in IDS.items():
            session.add(User(id=uid, subject=SUBJECTS[who], username='synthetic_' + who,
                display_name='Synthetic tester', created_at=NOW - timedelta(days=1),
                cardless_trial_started_at=NOW - timedelta(days=1),
                cardless_trial_ends_at=NOW + timedelta(days=29)))
    return db


def auth(who):
    return {'Authorization': 'Bearer ' + who}


@asynccontextmanager
async def application(db, calls, provider_handler=None, **options):
    def provider(request):
        calls.append(request)
        return provider_handler(request) if provider_handler else response()
    app = create_app(settings(deepseek_api_key='synthetic_only', enforce_subscriptions=True, **options),
        database=db, verifier=Verifier(), clock=lambda: NOW, store_providers={},
        bot_transport=httpx.MockTransport(provider))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://test') as client:
            yield client
    finally:
        await app.state.bot.close()
        await app.state.pubsub_verifier.close()


async def register(client, who='owner', *, replace=False):
    device, secret = str(uuid4()), secrets.token_urlsafe(32)
    result = await client.post('/v1/devices', headers=auth(who), json={
        'device_id': device, 'secret': secret, 'replace_active': replace})
    assert result.status_code == 200, result.text
    return auth(who) | {'X-Vipi-Device-ID': device, 'X-Vipi-Device-Secret': secret}


async def send(client, headers, request_id=None, **body):
    return await client.post('/v1/bot/messages', headers=headers, json={
        'request_id': request_id or str(uuid4()), 'consent_version': 'deepseek-v1',
        'messages': [{'role': 'user', 'content': 'Synthetic hello'}], **body})


async def reservations(db):
    async with db.sessions() as session:
        return (await session.execute(select(Reservation))).scalars().all()


async def test_wrong_shared_pin_does_not_grant_actual_profile_and_exact_UUID_remedy_preserves_it(owned_accounts):
    calls = []
    async with application(owned_accounts, calls, reviewer_identity_subjects={SUBJECTS['pinned']}) as client:
        owner_headers = await register(client)
        before = (await client.get('/v1/me', headers=auth('owner'))).json()
        state = (await client.get('/v1/entitlements', headers=auth('owner'))).json()
        trial = state['base']['cardless_trial']
        assert state['base']['active'] and not state['bot_mini']['active']
        assert not (await client.get('/v1/bot/allowance', headers=auth('owner'))).json()['available']
        denied = await send(client, owner_headers)
        assert denied.status_code == 402 and denied.json() == {'error': 'bot_subscription_required'}
        assert not calls and not await reservations(owned_accounts)
        # A separately pinned shared identity is genuinely entitled; no email or
        # similar subject text implicitly joins it to either other account.
        assert (await client.get('/v1/entitlements', headers=auth('pinned'))).json()['bot_mini']['active']
        assert not (await client.get('/v1/entitlements', headers=auth('legacy'))).json()['bot_mini']['active']

    # Existing config-only grant mechanism, as on an application restart. No
    # relinking, device replacement, new profile or synthetic purchase record.
    async with application(owned_accounts, calls, reviewer_identity_subjects={SUBJECTS['pinned']},
                           reviewer_user_ids={OWNER}) as client:
        assert (await client.get('/v1/me', headers=auth('owner'))).json() == before
        state = (await client.get('/v1/entitlements', headers=auth('owner'))).json()
        assert state['base']['cardless_trial'] == trial
        for plan in ('base', 'bot_mini'):
            assert state[plan]['active'] and state[plan]['access_source'] == 'review_complimentary'
        assert not (await client.get('/v1/entitlements', headers=auth('legacy'))).json()['bot_mini']['active']
        assert (await client.get('/v1/entitlements', headers=auth('pinned'))).json()['bot_mini']['active']
        sent = await send(client, owner_headers)
        assert sent.status_code == 200 and len(calls) == 1
        assert sent.json()['allowance']['remaining_replies'] == 149
    async with owned_accounts.sessions() as session:
        assert not (await session.execute(select(Entitlement))).scalars().all()
        devices = (await session.execute(select(Device).where(Device.user_id == OWNER))).scalars().all()
        assert len(devices) == 1 and devices[0].active
        assert devices[0].id == owner_headers['X-Vipi-Device-ID']
        user = await session.get(User, OWNER)
        assert user.subject == SUBJECTS['owner']


async def test_available_allowance_does_not_authorize_revoked_foreign_or_missing_device(owned_accounts):
    calls = []
    async with application(owned_accounts, calls, reviewer_user_ids={OWNER}, bot_monthly_replies=2) as client:
        old = await register(client)
        current = await register(client, replace=True)
        foreign = await register(client, 'pinned')
        # Allowance is account-level, not a device-authorization proof.
        allowance = await client.get('/v1/bot/allowance', headers=old)
        assert allowance.status_code == 200 and allowance.json()['available']
        for headers in (old, auth('owner'), foreign | auth('owner'),
                        current | {'X-Vipi-Device-Secret': secrets.token_urlsafe(32)}):
            denied = await send(client, headers)
            assert denied.status_code == 401 and denied.json() == {'error': 'device_revoked'}
        malformed = await send(client, current | {'X-Vipi-Device-Secret': 'too_short'})
        assert malformed.status_code == 401 and malformed.json() == {'error': 'invalid_device_credential'}
        assert not calls and not await reservations(owned_accounts)
        request_id = str(uuid4())
        result = await send(client, current, request_id)
        assert result.status_code == 200 and result.json()['allowance']['remaining_replies'] == 1
        duplicate = await send(client, current, request_id)
        assert duplicate.status_code == 409 and duplicate.json() == {'error': 'request_already_used'}
        second = await send(client, current)
        assert second.status_code == 200 and second.json()['allowance']['remaining_replies'] == 0
        exhausted = await send(client, current)
        assert exhausted.status_code == 429 and exhausted.json() == {'error': 'monthly_allowance_reached'}
        assert exhausted.headers['Retry-After'] == '60'
        assert len(calls) == 2 and len(await reservations(owned_accounts)) == 2


async def test_existing_device_works_after_fresh_auth_window_without_reregistering(owned_accounts):
    calls = []
    async with application(owned_accounts, calls, reviewer_user_ids={OWNER}) as client:
        registered = await register(client)
        old_auth = registered | auth('owner_old')
        # auth_time is old, while the injected verifier represents an otherwise
        # valid token. Signature/expiry verification is covered separately.
        assert (await client.get('/v1/keys', headers=old_auth)).status_code == 200
        denied = await client.post('/v1/devices', headers=auth('owner_old'), json={
            'device_id': registered['X-Vipi-Device-ID'], 'secret': registered['X-Vipi-Device-Secret']})
        assert denied.status_code == 401 and denied.json() == {'error': 'recent_sign_in_required'}
        assert not await reservations(owned_accounts)
        sent = await send(client, old_auth)
        assert sent.status_code == 200 and len(calls) == 1
        async with owned_accounts.sessions() as session:
            devices = (await session.execute(select(Device).where(Device.user_id == OWNER))).scalars().all()
            assert len(devices) == 1 and devices[0].active


async def test_complimentary_grant_never_bypasses_auth_floor_or_provider_consent(owned_accounts):
    calls = []
    async with application(owned_accounts, calls, reviewer_user_ids={OWNER}) as client:
        registered = await register(client)
        async with owned_accounts.sessions.begin() as session:
            (await session.get(User, OWNER)).minimum_auth_time = int(NOW.timestamp())
        for path in ('/v1/me', '/v1/entitlements', '/v1/bot/allowance'):
            rejected = await client.get(path, headers=auth('owner_old'))
            assert rejected.status_code == 401 and rejected.json() == {'error': 'recent_sign_in_required'}
        rejected = await send(client, registered | auth('owner_old'))
        assert rejected.status_code == 401 and rejected.json() == {'error': 'recent_sign_in_required'}
        unauthenticated = await send(client, {})
        assert unauthenticated.status_code == 401 and unauthenticated.json() == {'error': 'sign_in_required'}
        rejected = await send(client, registered, consent_version='unaccepted_version')
        assert rejected.status_code == 400 and rejected.json() == {'error': 'bot_consent_required'}
        assert not calls and not await reservations(owned_accounts)
        assert (await send(client, registered)).status_code == 200
        assert len(calls) == 1


@pytest.mark.parametrize('outcome', ['uncertain_timeout', 'definite_rejection'])
async def test_HTTP_provider_errors_preserve_no_replay_and_correct_quota(owned_accounts, outcome):
    calls = []
    def provider(request):
        if outcome == 'uncertain_timeout':
            raise httpx.ReadTimeout('private_synthetic_provider_detail')
        return httpx.Response(429, text='private_synthetic_provider_detail')
    async with application(owned_accounts, calls, reviewer_user_ids={OWNER},
                           provider_handler=provider) as client:
        registered = await register(client)
        request_id = str(uuid4())
        denied = await send(client, registered, request_id)
        expected = 'bot_reply_unconfirmed' if outcome == 'uncertain_timeout' else 'bot_unavailable'
        assert denied.status_code == 503 and denied.json() == {'error': expected}
        assert 'private_synthetic_provider_detail' not in denied.text
        retry = await send(client, registered, request_id)
        assert retry.status_code == 409 and retry.json() == {'error': 'request_already_used'}
        assert len(calls) == 1
        rows = await reservations(owned_accounts)
        assert len(rows) == 1
        row = rows[0]
        allowance = (await client.get('/v1/bot/allowance', headers=auth('owner'))).json()
        if outcome == 'uncertain_timeout':
            assert row.state == 'uncertain' and row.actual_nano_usd is None
            assert allowance['remaining_replies'] == 149
        else:
            assert row.state == 'settled' and row.actual_nano_usd == 0
            assert allowance['remaining_replies'] == 150
