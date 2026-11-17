"""Recovery startup boundary: no live databases, accounts, providers or workers."""
from types import SimpleNamespace
import importlib

import httpx
import pytest
from pydantic import ValidationError

from vipi.api import create_app
from vipi.config import Settings
from vipi.delivery import DeliveryError
from vipi.recovery_gate import SAFE_STATIC_PATHS


def settings(**kwargs):
    return Settings(database_url='sqlite+aiosqlite://', workos_client_id='client_fixture',
                    workos_issuer='https://api.workos.com', service_secret='x'*43, **kwargs)


def bomb(*args, **kwargs):
    raise AssertionError('state/provider initialization must not occur')


@pytest.fixture
def held(monkeypatch):
    for module, attribute in [('vipi.api', 'Database'), ('vipi.api', 'WorkOSVerifier'),
                              ('vipi.store_providers', 'providers_for'), ('vipi.bot', 'BotGateway'),
                              ('vipi.events', 'InboxEvents')]:
        monkeypatch.setattr(importlib.import_module(module), attribute, bomb)
    # Test that injected dependencies are not touched either.
    return create_app(settings(recovery_hold=True), database=object(), verifier=object(), store_providers={})


async def test_held_lifespan_and_safe_static_get_head_without_state(held):
    from fastapi import FastAPI
    from vipi.public_pages import install, PAGES
    reference = FastAPI(); install(reference)
    async with held.router.lifespan_context(held):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=held), base_url='https://test') as client:
            assert (await client.get('/health/live')).json() == {'status': 'ok'}
            for path in SAFE_STATIC_PATHS:
                response = await client.get(path, headers={'Cookie': '__Host-vipi-delete-auth=ignored'})
                assert response.status_code == 200
                assert 'set-cookie' not in response.headers
                assert (await client.head(path)).status_code == 200
                if path in PAGES:
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=reference), base_url='https://test') as other:
                        assert response.content == (await other.get(path)).content
            guidance = (await client.get('/delete-account')).text
            assert 'does not submit or confirm' in guidance
            assert '/delete-account/sign-in' not in guidance
            ready = await client.get('/health/ready')
            assert ready.status_code == 503 and ready.json()['error'] == 'recovery_hold'
            assert (await client.head('/health/ready')).status_code == 503


@pytest.mark.parametrize('method,path', [
    ('GET','/v1/me'), ('PUT','/v1/me'), ('POST','/v1/messages'), ('DELETE','/v1/me'),
    ('POST','/v1/bot/reply'), ('POST','/v1/purchases/apple'),
    ('POST','/v1/store-notifications/apple'), ('GET','/delete-account/sign-in'),
    ('GET','/delete-account/callback'), ('POST','/delete-account/confirm'),
    ('POST','/privacy'), ('PUT','/health/live'), ('OPTIONS','/help'),
    ('GET','/privacy/'), ('GET','/unknown-new-route')])
async def test_all_state_paths_rejected_before_body_auth_or_dispatch(held, method, path):
    sent=[]
    async def receive():
        raise AssertionError('held request body must not be received')
    async def send(message): sent.append(message)
    await held({'type':'http', 'asgi':{'version':'3.0'}, 'method':method, 'path':path,
                'raw_path':path.encode(), 'query_string':b'', 'headers':[], 'scheme':'https',
                'http_version':'1.1', 'server':('test',443), 'client':('test',1)}, receive, send)
    assert sent[0]['status'] == 503
    assert b'recovery_hold' in sent[1]['body']


async def test_websocket_closes_before_accept_receive_or_auth(held):
    sent=[]
    async def receive(): raise AssertionError('no WebSocket handshake/auth input needed')
    async def send(message): sent.append(message)
    await held({'type':'websocket', 'asgi':{'version':'3.0'}, 'path':'/v1/events',
                'headers':[], 'query_string':b'', 'scheme':'wss'}, receive, send)
    assert sent == [{'type':'websocket.close','code':1013,'reason':'recovery_hold'}]


@pytest.mark.parametrize('name', ['billing_worker','maintenance','push'])
async def test_workers_return_before_db_provider_initialization(monkeypatch, name):
    module = importlib.import_module('vipi.'+name)
    monkeypatch.setattr(module, 'Database', bomb)
    if name == 'push':
        import vipi.config
        monkeypatch.setattr(vipi.config, 'Settings', lambda: settings(recovery_hold=True))
        monkeypatch.setattr(module, 'PushProviders', bomb)
    else:
        monkeypatch.setattr(module, 'Settings', lambda: settings(recovery_hold=True))
        if name == 'billing_worker': monkeypatch.setattr(module, 'providers_for', bomb)
        if name == 'maintenance': monkeypatch.setattr(module, 'expire_deletion_receipts', bomb)
    await module.main()


@pytest.mark.parametrize('command', ['resolve','suspend','restore'])
async def test_operator_mutations_refused_before_db(monkeypatch, command):
    from vipi import moderation
    monkeypatch.setattr(moderation, 'Settings', lambda: settings(recovery_hold=True))
    monkeypatch.setattr(moderation, 'Database', bomb)
    with pytest.raises(DeliveryError) as error:
        await moderation.run(SimpleNamespace(command=command))
    assert error.value.code == 'recovery_hold' and error.value.status == 503


async def test_default_deployment_and_injected_dependencies_unchanged():
    from test_api import TestVerifier
    assert settings().recovery_hold is False
    # The ordinary route still performs authentication, not recovery rejection.
    app = create_app(settings(), database=object(), verifier=TestVerifier(), store_providers={})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://test') as client:
        assert (await client.get('/v1/me')).status_code == 401
    await app.state.bot.close()
    await app.state.pubsub_verifier.close()


def test_startup_environment_explicit_and_invalid_value_rejected(monkeypatch):
    monkeypatch.setenv('VIPI_RECOVERY_HOLD','true')
    assert settings().recovery_hold is True
    monkeypatch.setenv('VIPI_RECOVERY_HOLD','false')
    assert settings().recovery_hold is False
    monkeypatch.setenv('VIPI_RECOVERY_HOLD','not-a-bool')
    with pytest.raises(ValidationError): settings()
