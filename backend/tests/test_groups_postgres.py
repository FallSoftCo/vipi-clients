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


async def test_cancel_and_late_mutation_serialize_to_exactly_one_durable_outcome(db):
    if db.engine.dialect.name != "postgresql":
        pytest.skip("requires disposable PostgreSQL row locks")
    from test_groups_operation_recovery import cancel
    from vipi.db import GroupCancellation,GroupOperation
    gid,request=await create(db),str(uuid4())
    async def admit():
        try:
            return await change(db,gid,"rename",request_id=request,epoch=1,title="Prepared",device_id="alice-phone")
        except DeliveryError as error:return error.code
    result=await asyncio.wait_for(asyncio.gather(cancel(db,gid,request,title="Prepared"),admit()),10)
    async with db.sessions() as session:
        fence=await session.get(GroupCancellation,(gid,"alice",request))
        receipt=await session.get(GroupOperation,(gid,request))
        if result[0]["status"]=="cancelled":
            assert result[1]=="group_operation_cancelled" and fence and receipt is None
            assert (await current(db,gid))["epoch"]==1
        else:
            assert result[0]["result"]==result[1] and receipt and fence is None
            assert (await current(db,gid))["epoch"]==2


async def test_cancel_and_atomic_control_race_never_leaks_losing_envelopes(db):
    if db.engine.dialect.name != "postgresql":
        pytest.skip("requires disposable PostgreSQL row locks")
    from dataclasses import replace
    from test_groups_operation_recovery import cancel
    from test_groups_atomic import atomic
    from vipi.db import GroupMessage
    gid=await create(db);await join(db,gid,"bob")
    body=replace(fanout(await current(db,gid),("bob",)),kind="control");request=str(uuid4())
    async def admit():
        try:return await atomic(db,gid,"role",body,request_id=request,target_id="bob",role="admin")
        except DeliveryError as error:return error.code
    result=await asyncio.wait_for(asyncio.gather(cancel(db,gid,request,action="role",epoch=body.epoch,
        target_id="bob",role="admin",control=body),admit()),10)
    async with db.sessions() as session:
        queued=await session.get(PendingMessage,body.envelopes[0].id)
        control=await session.get(GroupMessage,(gid,body.id))
        member=await session.get(GroupMember,(gid,"bob"))
        if result[0]["status"]=="cancelled":
            assert result[1]=="group_operation_cancelled" and queued is None and control is None
            assert member.role=="member"
        else:
            assert result[0]["result"]==result[1] and queued and control and member.role=="admin"


async def test_cancel_and_standalone_control_admission_share_the_same_lock_fence(db):
    if db.engine.dialect.name != "postgresql":
        pytest.skip("requires disposable PostgreSQL row locks")
    from dataclasses import replace
    from test_groups_operation_recovery import cancel
    from vipi.db import GroupMessage
    gid=await create(db);await join(db,gid,"bob")
    body=replace(fanout(await current(db,gid),("bob",)),kind="control")
    async def admit():
        try:
            async with db.sessions.begin() as session:
                return await groups.send(session,group_id=gid,actor_id="alice",device_id="alice-phone",fanout=body,now=NOW)
        except DeliveryError as error:return error.code
    result=await asyncio.wait_for(asyncio.gather(cancel(db,gid,body.id,action="control",epoch=body.epoch,control=body),admit()),10)
    async with db.sessions() as session:
        queued=await session.get(PendingMessage,body.envelopes[0].id)
        control=await session.get(GroupMessage,(gid,body.id))
        if result[0]["status"]=="cancelled":
            assert result[1]=="group_operation_cancelled" and queued is None and control is None
        else:
            assert result[0]["result"]==result[1] and queued and control
