import base64
import secrets
from uuid import uuid4

import httpx
import pytest_asyncio
import pytest

from conftest import NOW
from vipi.api import create_app
from vipi.auth import AuthenticationError, Principal
from vipi.config import Settings


class TestVerifier:
    __test__ = False
    async def verify(self, token):
        if token not in ("alice", "bob", "eve"):
            raise AuthenticationError("invalid")
        return Principal("user_qa_" + token, "session_" + token, int(NOW.timestamp()))


@pytest_asyncio.fixture
async def api(db):
    settings = Settings(database_url="sqlite+aiosqlite://", workos_client_id="client_fixture",
                        workos_issuer="https://api.workos.com", service_secret="a" * 43)
    app = create_app(settings, database=db, verifier=TestVerifier(), clock=lambda: NOW)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://vipi.test") as client:
        yield client


async def identity(api, who):
    headers = {"Authorization": "Bearer " + who}
    result = await api.put("/v1/me", json={"username": "qa_" + who, "display_name": who.title()}, headers=headers)
    assert result.status_code == 200, result.text
    user = result.json()
    device_id, secret = str(uuid4()), secrets.token_urlsafe(32)
    result = await api.post("/v1/devices", headers=headers, json={"device_id": device_id, "secret": secret})
    assert result.status_code == 200, result.text
    return user, device_id, headers | {"X-Vipi-Device-ID": device_id, "X-Vipi-Device-Secret": secret}


async def test_registration_exact_lookup_and_private_email(api):
    alice, _, headers = await identity(api, "alice")
    bob, _, _ = await identity(api, "bob")
    result = await api.get("/v1/people/qa_bob", headers=headers)
    assert result.status_code == 200 and result.json() == bob
    assert set(result.json()) == {"id", "username", "display_name"}
    assert (await api.get("/v1/people/qa_b", headers=headers)).status_code == 404
    assert (await api.get("/v1/me")).status_code == 401
    assert (await api.get("/v1/me", headers={"Authorization": "Bearer bogus"})).status_code == 401
    for _ in range(28):
        await api.get("/v1/people/nobody", headers=headers)
    assert (await api.get("/v1/people/qa_bob", headers=headers)).status_code == 429


async def test_delivery_receipt_and_cross_account_access(api):
    alice, alice_device, alice_headers = await identity(api, "alice")
    bob, bob_device, bob_headers = await identity(api, "bob")
    _, _, eve_headers = await identity(api, "eve")
    envelope = {"id": str(uuid4()), "recipient_id": bob["id"], "recipient_device_id": bob_device,
                "created_at": NOW.isoformat(), "cipher_type": 3, "ciphertext": base64.b64encode(b"opaque fixture, not real encryption" * 2).decode()}
    response = await api.post("/v1/messages", headers=alice_headers, json=envelope)
    assert response.status_code == 200 and response.json()["state"] == "accepted"
    assert (await api.post("/v1/messages", headers=alice_headers, json=envelope)).json() == response.json()
    inbox = (await api.get("/v1/messages/pending", headers=bob_headers)).json()["messages"]
    assert len(inbox) == 1 and inbox[0]["ciphertext"] == envelope["ciphertext"] and inbox[0]["sender_id"] == alice["id"]
    message_url = "/v1/messages/" + envelope["id"]
    assert (await api.get(message_url, headers=eve_headers)).status_code == 404
    assert (await api.post(message_url + "/receipt", headers=eve_headers)).status_code == 404
    # A legitimate account token cannot use another phone's device credential.
    stolen = alice_headers | {"Authorization": "Bearer eve"}
    assert (await api.get(message_url, headers=stolen)).status_code == 401
    assert (await api.post(message_url + "/receipt", headers=bob_headers)).json()["state"] == "delivered"
    assert (await api.get("/v1/messages/pending", headers=bob_headers)).json()["messages"] == []
    assert (await api.get(message_url, headers=alice_headers)).json()["state"] == "delivered"


async def test_blocking_and_replacement_are_explicit(api):
    alice, _, alice_headers = await identity(api, "alice")
    bob, _, bob_headers = await identity(api, "bob")
    assert (await api.get("/v1/blocks/" + alice["id"], headers=bob_headers)).json() == {"blocked": False}
    assert (await api.put("/v1/blocks/" + alice["id"], headers=bob_headers, json={"blocked": True})).status_code == 200
    assert (await api.get("/v1/blocks/" + alice["id"], headers=bob_headers)).json() == {"blocked": True}
    assert (await api.get("/v1/blocks/" + bob["id"], headers=alice_headers)).json() == {"blocked": False}
    assert (await api.get("/v1/blocks/" + alice["id"], headers={"Authorization": "Bearer bob"})).status_code == 401
    assert (await api.get("/v1/people/qa_bob", headers=alice_headers)).status_code == 404
    assert (await api.put("/v1/blocks/" + alice["id"], headers=bob_headers, json={"blocked": False})).json() == {"blocked": False}
    assert (await api.get("/v1/people/qa_bob", headers=alice_headers)).status_code == 200
    registration = {"device_id": str(uuid4()), "secret": secrets.token_urlsafe(32)}
    assert (await api.post("/v1/devices", headers=alice_headers, json=registration)).status_code == 409
    registration["replace_active"] = True
    assert (await api.post("/v1/devices", headers=alice_headers, json=registration)).status_code == 200
    assert (await api.get("/v1/messages/pending", headers=alice_headers)).status_code == 401


async def test_inbox_cursor_passes_unreadable_items_and_survives_receipts(api):
    _, _, alice_headers = await identity(api, "alice")
    bob, bob_device, bob_headers = await identity(api, "bob")
    _, _, eve_headers = await identity(api, "eve")
    ids = set()
    for _ in range(105):
        message_id = str(uuid4()); ids.add(message_id)
        response = await api.post('/v1/messages', headers=alice_headers, json={
            'id': message_id, 'recipient_id': bob['id'], 'recipient_device_id': bob_device,
            'created_at': NOW.isoformat(), 'cipher_type': 3,
            'ciphertext': base64.b64encode(b'unreadable QA envelope' * 3).decode()})
        assert response.status_code == 200
    first = (await api.get('/v1/messages/pending', headers=bob_headers)).json()
    assert len(first['messages']) == 100 and first['next_cursor']
    params = {'after': first['next_cursor']}
    # Do not acknowledge the first page: unreadable messages must not starve later ones.
    second = (await api.get('/v1/messages/pending', headers=bob_headers, params=params)).json()
    assert len(second['messages']) == 5 and second['next_cursor'] is None
    assert {x['id'] for x in first['messages'] + second['messages']} == ids
    # Cursor remains valid after its own boundary row has been acknowledged.
    assert (await api.post('/v1/messages/' + first['messages'][-1]['id'] + '/receipt', headers=bob_headers)).status_code == 200
    assert (await api.get('/v1/messages/pending', headers=bob_headers, params=params)).json() == second
    assert (await api.get('/v1/messages/pending', headers=eve_headers, params=params)).status_code == 400
    changed = ('A' if first['next_cursor'][0] != 'A' else 'B') + first['next_cursor'][1:]
    assert (await api.get('/v1/messages/pending', headers=bob_headers, params={'after':changed})).status_code == 400
    assert (await api.get('/v1/messages/pending', headers=bob_headers, params={'after':'invalid'})).status_code == 400


async def test_sensitive_validation_input_is_not_echoed_and_large_body_rejected(api):
    value = "sensitive-test-value"
    result = await api.post("/v1/devices", headers={"Authorization": "Bearer alice"}, json={"device_id": value, "secret": value})
    assert result.status_code == 422 and value not in result.text
    async def chunks():
        yield b"x" * 60_000
        yield b"x" * 60_000
    assert (await api.post("/v1/devices", content=chunks())).status_code == 413


async def test_staging_access_requires_real_verification_then_explicit_subject(db):
    # Inert PG config; the fixture Database is explicitly injected below.
    settings = Settings(database_url="postgresql+asyncpg://fixture.invalid/vipi_test", workos_client_id="client_fixture",
        workos_issuer="https://api.workos.com", service_secret="a" * 43, environment="staging")
    with pytest.raises(ValueError, match="allowlist"):
        create_app(settings, database=db, verifier=TestVerifier())
    app = create_app(settings.model_copy(update={"allowed_subjects": frozenset({"user_qa_alice"})}),
        database=db, verifier=TestVerifier(), clock=lambda: NOW)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://vipi.test") as client:
        assert (await client.put("/v1/me", headers={"Authorization": "Bearer alice"}, json={"username": "staging_alice", "display_name": "QA"})).status_code == 200
        assert (await client.get("/v1/me", headers={"Authorization": "Bearer bob"})).status_code == 403
        assert (await client.get("/v1/me", headers={"Authorization": "Bearer user_qa_alice"})).status_code == 401
