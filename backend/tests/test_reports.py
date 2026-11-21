import base64
import json
import secrets
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from conftest import NOW
from test_api import api, identity
from vipi.db import ModerationAction, PendingMessage, User, UserReport
from vipi.deletion import request_deletion
from vipi.delivery import DeliveryError, Envelope, accept
from vipi.reports import report_cipher, restrict, submit


async def test_report_requires_explicit_selection_device_and_idempotent_body(api, db):
    alice, _, headers = await identity(api, "alice")
    bob, _, _ = await identity(api, "bob")
    body = {"report_id": str(uuid4()), "reported_user_id": bob["id"], "message_id": str(uuid4()),
        "selected_text": "Only this original incoming message.", "reason": "harassment", "consent_version": "report-v1"}
    assert (await api.post("/v1/reports", json=body, headers={"Authorization":"Bearer alice"})).status_code == 401
    assert (await api.post("/v1/reports", json=body | {"consent_version":""}, headers=headers)).status_code == 400
    result = await api.post("/v1/reports", json=body, headers=headers)
    assert result.status_code == 202 and result.json() == {"reported":True, "report_id":body["report_id"]}
    assert (await api.post("/v1/reports", json=body, headers=headers)).json() == result.json()
    assert (await api.post("/v1/reports", json=body | {"selected_text":"changed"}, headers=headers)).status_code == 409
    limited = await api.post("/v1/reports", headers=headers, json=body | {"report_id": str(uuid4())})
    assert limited.status_code == 429 and limited.headers["Retry-After"] == "60"
    async with db.sessions() as session:
        record = await session.get(UserReport, body["report_id"])
        assert body["selected_text"].encode() not in record.payload
        decoded = json.loads(report_cipher("a" * 43).decrypt(record.payload))
        assert decoded["selected_text"] == body["selected_text"]
        assert decoded["participants_corroborated"] is False
        assert (record.expires_at.replace(tzinfo=NOW.tzinfo) - NOW) == timedelta(days=30)


async def test_report_bound_to_participants_when_relay_record_exists(api, db):
    alice, alice_device, alice_headers = await identity(api, "alice")
    bob, bob_device, bob_headers = await identity(api, "bob")
    eve, _, eve_headers = await identity(api, "eve")
    message_id = str(uuid4())
    sent = await api.post("/v1/messages", headers=alice_headers, json={"id":message_id,
        "recipient_id":bob["id"], "recipient_device_id":bob_device,"created_at":NOW.isoformat(),
        "cipher_type":3,"ciphertext":base64.b64encode(b"opaque test payload" * 3).decode()})
    assert sent.status_code == 200
    body = {"report_id":str(uuid4()), "reported_user_id":alice["id"],"message_id":message_id,
        "selected_text":"Reporter-selected text", "reason":"spam", "consent_version":"report-v1"}
    assert (await api.post("/v1/reports", headers=eve_headers,json=body)).status_code == 400
    # Blocking does not remove the ability to report what happened.
    await api.put("/v1/blocks/"+alice["id"],headers=bob_headers,json={"blocked":True})
    assert (await api.post("/v1/reports",headers=bob_headers,json=body)).status_code == 202
    async with db.sessions() as session:
        record = await session.get(UserReport,body["report_id"])
        assert json.loads(report_cipher("a"*43).decrypt(record.payload))["participants_corroborated"] is True


async def test_reports_have_strict_utf8_size_daily_bound_and_no_auto_suspension(db):
    async def send(**changes):
        values = dict(user_id="alice",report_id=str(uuid4()),reported_user_id="bob",message_id="message",
            selected_text="original",reason="other",consent_version="report-v1",secret="secret",now=NOW)
        values.update(changes)
        async with db.sessions.begin() as session:
            return await submit(session,**values)
    for changes in ({"selected_text":"é"*16385},{"selected_text":"\ud800"},{"selected_text":" "},{"message_id":None}):
        with pytest.raises(DeliveryError,match="invalid_report"):
            await send(**changes)
    for _ in range(20):
        await send()
    with pytest.raises(DeliveryError,match="report_limit_reached"):
        await send()
    async with db.sessions() as session:
        assert not (await session.get(User,"bob")).suspended
        assert (await session.execute(select(func.count()).select_from(UserReport))).scalar_one() == 20


async def test_operator_restriction_blocks_transport_preserves_deletion_and_can_restore(api,db):
    alice, alice_device, alice_headers = await identity(api,"alice")
    bob, bob_device, bob_headers = await identity(api,"bob")
    async with db.sessions.begin() as session:
        assert await restrict(session,user_id=alice["id"],suspended=True,operator="test-operator",reason="spam",now=NOW)
    assert (await api.get("/v1/me",headers=alice_headers)).json() == {"error":"account_restricted"}
    assert (await api.get("/v1/entitlements",headers=alice_headers)).status_code == 200
    assert (await api.get("/v1/people/qa_alice",headers=bob_headers)).status_code == 404
    async with db.sessions.begin() as session:
        with pytest.raises(DeliveryError):
            await accept(session,Envelope(id=str(uuid4()),sender_id=alice["id"],sender_device_id=alice_device,
                recipient_id=bob["id"],recipient_device_id=bob_device,created_at=NOW,cipher_type=3,ciphertext=b"x"*64),now=NOW)
    async with db.sessions.begin() as session:
        assert await restrict(session,user_id=alice["id"],suspended=False,operator="test-operator",reason="appeal",now=NOW)
    assert (await api.get("/v1/me",headers=alice_headers)).status_code == 200
    async with db.sessions.begin() as session:
        await submit(session,user_id=bob["id"],report_id=str(uuid4()),reported_user_id=alice["id"],message_id=None,
            selected_text=None,reason="spam",consent_version="report-v1",secret="a"*43,now=NOW)
        await restrict(session,user_id=alice["id"],suspended=True,operator="test-operator",reason="spam",now=NOW)
    async with db.sessions.begin() as session:
        await request_deletion(session,subject="user_qa_alice",account_id=alice["id"],
            receipt_secret=secrets.token_urlsafe(32),service_secret="a"*43,now=NOW)
    async with db.sessions() as session:
        assert await session.get(User,alice["id"]) is None
        assert not (await session.execute(select(UserReport))).scalars().all()
        assert not (await session.execute(select(ModerationAction))).scalars().all()
