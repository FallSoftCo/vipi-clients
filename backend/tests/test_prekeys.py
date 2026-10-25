"""Directory semantics with inert public-sized bytes. These tests do not assert
cryptographic validity; native interop tests must verify real bundle signatures.
"""
import base64
import copy
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from conftest import NOW
from test_api import api, identity
from vipi.db import KeyClaim, PublicPreKey
from vipi.delivery import DeliveryError
from vipi.prekeys import PublishInput, claim, expire_claims, publish


def publication(revision=1, first=1, count=5):
    b64 = lambda size, value: base64.b64encode(bytes([value]) * size).decode()
    return {"revision": revision, "registration_id": 101, "identity_key": b64(33, 5),
        "signed": {"id": 1, "key": b64(33, 6), "signature": b64(64, 7)},
        "one_time": [{"id": i, "ec_key": b64(33, 8), "key": b64(1569, 9), "signature": b64(64, 10)}
                     for i in range(first, first + count)]}


async def test_claim_retries_never_resurrect_or_reallocate_keys(api, db):
    alice, _, a = await identity(api, "alice")
    bob, bdevice, b = await identity(api, "bob")
    body = publication()
    assert (await api.put("/v1/keys", json=body, headers=b)).json() == {"revision": 1, "remaining": 5}
    request = {"request_id": str(uuid4())}
    url = f'/v1/people/{bob["id"]}/keys'
    first = await api.post(url, json=request, headers=a)
    assert first.status_code == 200 and first.json()["one_time"]["id"] == 1
    assert first.json()["device_id"] == bdevice and first.json()["signal_device_id"] == 1
    assert (await api.post(url, json=request, headers=a)).json() == first.json()
    # Lost publication response followed by retry cannot reinsert consumed keys.
    assert (await api.put("/v1/keys", json=body, headers=b)).json() == {"revision": 1, "remaining": 4}
    assert (await api.get("/v1/keys", headers=b)).json()["remaining"] == 4
    changed = copy.deepcopy(body); changed["identity_key"] = changed["signed"]["key"]
    assert (await api.put("/v1/keys", json=changed, headers=b)).json()["error"] == "key_revision_conflict"
    next_body = publication(2, 6, 2)
    changed = copy.deepcopy(next_body); changed["identity_key"] = changed["signed"]["key"]
    assert (await api.put("/v1/keys", json=changed, headers=b)).json()["error"] == "identity_replacement_required"
    assert (await api.put("/v1/keys", json=publication(2, 1), headers=b)).json()["error"] == "key_id_reuse"
    assert (await api.put("/v1/keys", json=next_body, headers=b)).json() == {"revision": 2, "remaining": 6}
    assert (await api.put("/v1/keys", json=body, headers=b)).status_code == 409
    async with db.sessions() as s:
        assert (await s.execute(select(func.count()).select_from(KeyClaim))).scalar_one() == 1


async def test_block_replacement_and_foreign_device_prevent_claims(api, db):
    alice, _, a = await identity(api, "alice")
    bob, old_device, b = await identity(api, "bob")
    _, _, e = await identity(api, "eve")
    await api.put("/v1/keys", json=publication(), headers=b)
    request = {"request_id": str(uuid4())}; url = f'/v1/people/{bob["id"]}/keys'
    assert (await api.post(url, json=request, headers=a)).status_code == 200
    assert (await api.post(url, json=request, headers=a | {"Authorization": "Bearer eve"})).status_code == 401
    await api.put('/v1/blocks/' + alice["id"], json={"blocked": True}, headers=b)
    assert (await api.post(url, json=request, headers=a)).status_code == 404
    await api.put('/v1/blocks/' + alice["id"], json={"blocked": False}, headers=b)
    new = {"device_id": str(uuid4()), "secret": "a" * 43, "replace_active": True}
    assert (await api.post("/v1/devices", json=new, headers=b)).status_code == 200
    assert (await api.post(url, json=request, headers=a)).json()["error"] == "recipient_identity_changed"
    assert (await api.put("/v1/keys", json=publication(2, 6), headers=b)).status_code == 401
    assert (await api.post(url, json={"request_id": str(uuid4())}, headers=a)).json()["error"] == "recipient_keys_unavailable"
    async with db.sessions() as s:
        assert (await s.execute(select(func.count()).select_from(PublicPreKey).where(PublicPreKey.device_id == old_device))).scalar_one() == 0


async def test_publication_bounds_and_claim_exhaustion(api):
    _, _, a = await identity(api, "alice")
    bob, _, b = await identity(api, "bob")
    body = publication(count=1)
    for mutation in (lambda b: b.update(private_key="secret-marker"),
                     lambda b: b["one_time"][0].update(key="bad"),
                     lambda b: b.update(one_time=b["one_time"] * 2),
                     lambda b: b.update(revision=True)):
        invalid = copy.deepcopy(body); mutation(invalid)
        result = await api.put("/v1/keys", json=invalid, headers=b)
        assert result.status_code == 422 and "secret-marker" not in result.text
    assert (await api.put("/v1/keys", json=body, headers=b)).status_code == 200
    url = '/v1/people/' + bob["id"] + '/keys'
    assert (await api.post(url, json={"request_id": str(uuid4())}, headers=a)).status_code == 200
    assert (await api.post(url, json={"request_id": str(uuid4())}, headers=a)).json()["error"] == "recipient_keys_unavailable"


async def test_expired_claim_cannot_consume_another_key(db):
    args = dict(user_id="alice", device_id="alice-phone", recipient_id="bob", request_id=str(uuid4()))
    async with db.sessions.begin() as s:
        await publish(s, user_id="bob", device_id="bob-phone", body=PublishInput(**publication()))
        await claim(s, **args, now=NOW)
    with pytest.raises(DeliveryError, match="key_claim_expired"):
        async with db.sessions.begin() as s:
            await claim(s, **args, now=NOW + timedelta(minutes=10))
    async with db.sessions.begin() as s:
        assert (await s.execute(select(func.count()).select_from(PublicPreKey))).scalar_one() == 4
        await expire_claims(s, NOW + timedelta(hours=72))
        assert (await s.execute(select(func.count()).select_from(KeyClaim))).scalar_one() == 0
