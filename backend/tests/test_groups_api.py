"""HTTP/device authentication, routing and disabled upgrade boundary."""
import base64
from uuid import uuid4

import httpx
import pytest_asyncio

from conftest import NOW
from test_api import TestVerifier, identity
from vipi.api import create_app
from vipi.config import Settings


def uid():
    return str(uuid4())


def settings(**extra):
    return Settings(database_url="sqlite+aiosqlite://",workos_client_id="client_fixture",
        workos_issuer="https://api.workos.com",service_secret="a"*43,**extra)


@pytest_asyncio.fixture
async def api(db):
    app = create_app(settings(groups_enabled=True),database=db,verifier=TestVerifier(),clock=lambda:NOW)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="https://vipi.test") as client:
        yield client


async def create(api,headers):
    gid = uid()
    result = await api.post("/v1/groups",headers=headers,json={"id":gid,"title":"Friends"})
    assert result.status_code == 200,result.text
    return result.json()


async def invite_join(api,group,headers,who,who_headers):
    invite = uid()
    result = await api.post(f'/v1/groups/{group["id"]}/invitations',headers=headers,
        json={"request_id":invite,"expected_epoch":group["epoch"],"user_id":who["id"]})
    assert result.status_code == 200,result.text
    result = await api.post(f'/v1/groups/{group["id"]}/invitations/{invite}/accept',headers=who_headers,
        json={"request_id":uid(),"expected_epoch":result.json()["epoch"]})
    assert result.status_code == 200,result.text
    return result.json()


async def test_disabled_upgrade_leaves_free_direct_chat_unchanged(db):
    assert settings().groups_enabled is False
    app = create_app(settings(),database=db,verifier=TestVerifier(),clock=lambda:NOW)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="https://vipi.test") as api:
        _,_,ah = await identity(api,"alice")
        bob,bd,_ = await identity(api,"bob")
        assert (await api.get("/v1/groups",headers=ah)).json() == {"error":"groups_not_available"}
        result = await api.post("/v1/messages",headers=ah,json={"id":uid(),"recipient_id":bob["id"],
            "recipient_device_id":bd,"created_at":NOW.isoformat(),"cipher_type":3,"ciphertext":base64.b64encode(b"x"*64).decode()})
        assert result.status_code == 200


async def test_http_member_inbox_context_receipts_and_nonmember_access(api):
    alice,ad,ah = await identity(api,"alice")
    bob,bd,bh = await identity(api,"bob")
    _,_,eh = await identity(api,"eve")
    group = await create(api,ah)
    assert (await api.get('/v1/groups/'+group["id"],headers=eh)).status_code == 404
    assert (await api.get('/v1/groups/'+group["id"],headers={"Authorization":"Bearer alice"})).status_code == 401
    group = await invite_join(api,group,ah,bob,bh)
    body = {"id":uid(),"epoch":group["epoch"],"created_at":NOW.isoformat(),"envelopes":[{
        "id":uid(),"recipient_id":bob["id"],"recipient_device_id":bd,"cipher_type":3,
        "ciphertext":base64.b64encode(b"opaque fixture is not encryption"*2).decode()}]}
    path = '/v1/groups/'+group["id"]+'/messages'
    result = await api.post(path,headers=ah,json=body)
    assert result.status_code == 200,result.text
    assert (await api.post(path,headers=ah,json=body)).json() == result.json()
    inbox = (await api.get('/v1/messages/pending',headers=bh)).json()["messages"]
    assert len(inbox) == 1
    assert {key:inbox[0][key] for key in ("group_id","group_epoch","group_message_id")} == {
        "group_id":group["id"],"group_epoch":group["epoch"],"group_message_id":body["id"]}
    assert inbox[0]["sender_device_id"] == ad and inbox[0]["sender_id"] == alice["id"]
    assert (await api.post('/v1/messages/'+inbox[0]["id"]+'/receipt',headers=bh)).json()["state"] == "delivered"
    assert (await api.post(path,headers=ah,json=body)).json()["deliveries"][0]["state"] == "delivered"
    assert (await api.get('/v1/groups',headers=bh)).json()["groups"][0]["id"] == group["id"]


async def test_http_stale_epoch_tamper_validation_and_id_conflict(api):
    _,_,ah = await identity(api,"alice")
    group = await create(api,ah)
    path = '/v1/groups/'+group["id"]
    body = {"request_id":uid(),"expected_epoch":1,"title":"Renamed"}
    first = await api.patch(path,headers=ah,json=body)
    assert first.status_code == 200
    assert (await api.patch(path,headers=ah,json=body)).json() == first.json()
    assert (await api.patch(path,headers=ah,json=body|{"request_id":uid()})).json() == {"error":"group_epoch_changed"}
    assert (await api.patch(path,headers=ah,json=body|{"title":"tampered"})).json() == {"error":"group_request_conflict"}
    assert (await api.patch(path,headers=ah,json=body|{"secret":"must not echo"})).json() == {"error":"invalid_request"}
    assert (await api.post(path+'/messages',headers=ah,json={"id":uid(),"epoch":2,"created_at":NOW.isoformat(),"envelopes":[]})).status_code == 200


async def test_http_control_route_has_explicit_kind_and_invitee_binding(api):
    _,_,ah = await identity(api,"alice")
    bob,bd,bh = await identity(api,"bob")
    group = await create(api,ah)
    invite = uid()
    invitation = await api.post('/v1/groups/'+group["id"]+'/invitations',headers=ah,
        json={"request_id":invite,"expected_epoch":group["epoch"],"user_id":bob["id"]})
    assert invitation.status_code == 200
    body = {"id":uid(),"epoch":invitation.json()["epoch"],"created_at":NOW.isoformat(),"invited_user_id":bob["id"],
        "envelopes":[{"id":uid(),"recipient_id":bob["id"],"recipient_device_id":bd,"cipher_type":3,
            "ciphertext":base64.b64encode(b"opaque authenticated control fixture"*2).decode()}]}
    result = await api.post('/v1/groups/'+group["id"]+'/controls',headers=ah,json=body)
    assert result.status_code == 200,result.text
    inbox = (await api.get('/v1/messages/pending',headers=bh)).json()["messages"]
    assert len(inbox) == 1 and inbox[0]["group_kind"] == "control"
    assert inbox[0]["group_message_id"] == body["id"]


async def test_replaced_device_detected_again_after_membership_lock(api,db,monkeypatch):
    from sqlalchemy import update
    from vipi import groups
    from vipi.db import Device
    _,ad,ah = await identity(api,"alice")
    group = await create(api,ah)
    original = groups.mutate
    async def after_initial_credential_check(session,**args):
        # Model replacement committing between initial credential validation
        # and the membership's user lock. Deliberately keep ORM cache stale.
        await session.execute(update(Device).where(Device.id == ad).values(active=False)
            .execution_options(synchronize_session=False))
        return await original(session,**args)
    monkeypatch.setattr(groups,"mutate",after_initial_credential_check)
    result = await api.patch('/v1/groups/'+group["id"],headers=ah,
        json={"request_id":uid(),"expected_epoch":1,"title":"Must roll back"})
    assert result.status_code == 401 and result.json() == {"error":"device_revoked"}
    assert (await api.get('/v1/groups/'+group["id"],headers=ah)).json()["title"] == "Friends"


async def test_http_atomic_role_and_control_share_one_commit_and_admission(api):
    _,_,ah = await identity(api,"alice")
    bob,bd,bh = await identity(api,"bob")
    group = await invite_join(api,await create(api,ah),ah,bob,bh)
    control = {"id":uid(),"epoch":group["epoch"],"created_at":NOW.isoformat(),"envelopes":[{
        "id":uid(),"recipient_id":bob["id"],"recipient_device_id":bd,"cipher_type":3,
        "ciphertext":base64.b64encode(b"opaque control not real encryption"*2).decode()}]}
    body = {"request_id":uid(),"expected_epoch":group["epoch"],"role":"admin","control":control}
    path = '/v1/groups/'+group["id"]+'/members/'+bob["id"]
    result = await api.patch(path,headers=ah,json=body)
    assert result.status_code == 200,result.text
    assert result.json()["control_acceptance"]["admitted"] is True
    assert next(m for m in result.json()["members"] if m["user_id"]==bob["id"])["role"] == "admin"
    assert (await api.patch(path,headers=ah,json=body)).json() == result.json()


async def test_principal_revocation_is_rechecked_after_group_lock(api,db,monkeypatch):
    from sqlalchemy import update
    from vipi import groups
    from vipi.db import User
    alice,_,ah = await identity(api,"alice")
    group = await create(api,ah)
    original = groups.mutate
    async def revoked_before_lock(session,**args):
        # Simulate lifecycle/re-auth admission changing after the first token
        # check. The group lock refreshes the previously cached User object.
        await session.execute(update(User).where(User.id == alice["id"])
            .values(minimum_auth_time=int(NOW.timestamp())+1).execution_options(synchronize_session=False))
        return await original(session,**args)
    monkeypatch.setattr(groups,"mutate",revoked_before_lock)
    result = await api.patch('/v1/groups/'+group["id"],headers=ah,
        json={"request_id":uid(),"expected_epoch":1,"title":"Must roll back"})
    assert result.status_code == 401 and result.json() == {"error":"recent_sign_in_required"}
    assert (await api.get('/v1/groups/'+group["id"],headers=ah)).json()["title"] == "Friends"
