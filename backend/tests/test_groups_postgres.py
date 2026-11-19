"""Real row-lock race tests. Use only a disposable VIPI_TEST_POSTGRES_URL."""
import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select

from conftest import NOW
from test_groups import change, create, current, fanout, join
from vipi import groups
from vipi.db import GroupMember, PendingMessage
from vipi.delivery import DeliveryError


async def test_concurrent_epoch_mutations_commit_once(db):
    if db.engine.dialect.name != "postgresql":
        pytest.skip("requires disposable PostgreSQL row locks")
    gid = await create(db)
    async def rename(title):
        try:
            return await change(db,gid,"rename",epoch=1,title=title)
        except DeliveryError as error:
            return error.code
    result = await asyncio.wait_for(asyncio.gather(rename("First"),rename("Second")),10)
    assert sum(isinstance(value,dict) for value in result) == 1
    assert result.count("group_epoch_changed") == 1
    assert (await current(db,gid))["epoch"] == 2


async def test_send_and_leave_serialize_without_post_revocation_delivery(db):
    if db.engine.dialect.name != "postgresql":
        pytest.skip("requires disposable PostgreSQL row locks")
    gid = await create(db)
    await join(db,gid,"bob")
    body = fanout(await current(db,gid),("bob",))
    async def send():
        try:
            async with db.sessions.begin() as s:
                return await groups.send(s,group_id=gid,actor_id="alice",device_id="alice-phone",fanout=body,now=NOW)
        except DeliveryError as error:
            return error.code
    result = await asyncio.wait_for(asyncio.gather(send(),change(db,gid,"leave",actor="bob",epoch=body.epoch)),10)
    assert result[1] == {"left":True}
    assert isinstance(result[0],dict) or result[0] in ("group_epoch_changed","group_recipients_changed")
    async with db.sessions() as s:
        assert await s.get(GroupMember,(gid,"bob")) is None
        pending = (await s.scalars(select(PendingMessage).where(PendingMessage.group_id == gid))).all()
        assert all(p.state != "accepted" and p.ciphertext is None for p in pending)


async def test_concurrent_invite_acceptance_cannot_overfill_group(db):
    if db.engine.dialect.name != "postgresql":
        pytest.skip("requires disposable PostgreSQL row locks")
    from vipi.db import User
    gid = await create(db)
    invitations = {}
    for who in ("bob","eve"):
        invitations[who] = str(uuid4())
        await change(db,gid,"invite",target_id=who,request_id=invitations[who])
    async with db.sessions.begin() as s:
        for n in range(14):
            who = "extra"+str(n)
            s.add(User(id=who,subject=who,username=who,display_name=who,created_at=NOW))
        await s.flush()
        for n in range(14):
            s.add(GroupMember(group_id=gid,user_id="extra"+str(n),role="member",joined_epoch=1,joined_at=NOW))
    epoch = (await current(db,gid))["epoch"]
    async def accept(who):
        try:
            return await change(db,gid,"accept",actor=who,invite_id=invitations[who],epoch=epoch)
        except DeliveryError as error:
            return error.code
    result = await asyncio.wait_for(asyncio.gather(accept("bob"),accept("eve")),10)
    assert sum(isinstance(value,dict) for value in result) == 1
    assert result.count("group_epoch_changed") == 1
    assert len((await current(db,gid))["members"]) == 16


async def test_atomic_control_never_escapes_losing_epoch_race(db):
    if db.engine.dialect.name != "postgresql":
        pytest.skip("requires disposable PostgreSQL row locks")
    from dataclasses import replace
    from test_groups_atomic import atomic
    from vipi.db import GroupMessage
    gid = await create(db)
    await join(db,gid,"bob")
    body = replace(fanout(await current(db,gid),("bob",)),kind="control")
    async def role():
        try:
            return await atomic(db,gid,"role",body,target_id="bob",role="admin")
        except DeliveryError as error:
            return error.code
    async def rename():
        try:
            return await change(db,gid,"rename",epoch=body.epoch,title="Concurrent name")
        except DeliveryError as error:
            return error.code
    result = await asyncio.wait_for(asyncio.gather(role(),rename()),10)
    assert sum(isinstance(value,dict) for value in result) == 1
    assert result.count("group_epoch_changed") == 1
    async with db.sessions() as s:
        record = await s.get(GroupMessage,(gid,body.id))
        queued = await s.get(PendingMessage,body.envelopes[0].id)
        member = await s.get(GroupMember,(gid,"bob"))
        if isinstance(result[0],dict):
            assert record and queued and member.role == "admin"
        else:
            assert record is None and queued is None and member.role == "member"
