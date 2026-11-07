import asyncio
from datetime import timedelta
import secrets
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from conftest import NOW
from test_delivery import message
from vipi.accounts import register_device
from vipi.budget import BudgetError, reserve
from vipi.db import Device, PendingMessage, UsageBucket
from vipi.delivery import DeliveryError, accept
from vipi.prekeys import PublishInput, claim, publish
from test_prekeys import publication
from vipi.deletion import process_deletions, request_deletion
from vipi.db import AccountDeletion, User
from vipi.deletion import deletion_for, lock_account_lifecycle


@pytest.fixture(autouse=True)
def require_postgres(db):
    if db.engine.dialect.name != "postgresql":
        pytest.skip("Requires isolated real PostgreSQL; SQLite cannot prove row locking")


async def test_parallel_queue_admission_never_exceeds_cap(db):
    async def send():
        try:
            async with db.sessions.begin() as s:
                await accept(s, message(), now=NOW, max_pending=5)
            return "accepted"
        except DeliveryError as error:
            return error.code
    results = await asyncio.gather(*(send() for _ in range(25)))
    assert results.count("accepted") == 5
    assert results.count("recipient_queue_full") == 20
    async with db.sessions() as s:
        assert (await s.execute(select(func.count()).select_from(PendingMessage))).scalar_one() == 5


async def test_parallel_retries_accept_one_row(db):
    envelope = message()
    async def send():
        async with db.sessions.begin() as s:
            return (await accept(s, envelope, now=NOW)).id
    assert set(await asyncio.gather(*(send() for _ in range(20)))) == {envelope.id}
    async with db.sessions() as s:
        assert (await s.execute(select(func.count()).select_from(PendingMessage))).scalar_one() == 1


async def test_concurrent_budget_reservations_cannot_overspend(db):
    async def spend():
        try:
            async with db.sessions.begin() as s:
                await reserve(s, user_id="alice", request_id=str(uuid4()), maximum_cost=100_000_000, now=NOW)
            return "accepted"
        except BudgetError as error:
            return str(error)
    results = await asyncio.gather(*(spend() for _ in range(20)))
    assert results.count("accepted") == 5
    async with db.sessions() as s:
        assert (await s.get(UsageBucket, ("alice", "2026-10"))).reserved_nano_usd == 500_000_000


async def test_racing_replacement_and_delivery_leaves_no_old_identity_backlog(db):
    async def replace():
        async with db.sessions.begin() as s:
            await register_device(s, user_id="bob", device_id="bob-new", secret="a" * 43,
                replace_active=True, service_secret="b" * 43, now=NOW)
    async def send():
        try:
            async with db.sessions.begin() as s:
                await accept(s, message(), now=NOW)
        except DeliveryError as error:
            assert error.code == "recipient_identity_changed"
    await asyncio.gather(replace(), *(send() for _ in range(15)))
    async with db.sessions() as s:
        assert not (await s.get(Device, "bob-phone")).active
        assert (await s.get(Device, "bob-new")).active
        items = (await s.execute(select(PendingMessage))).scalars().all()
        assert all(item.ciphertext is None and item.state == "identity_changed" for item in items)


async def test_parallel_prekey_claims_allocate_once_and_retry_exactly(db):
    async with db.sessions.begin() as s:
        await publish(s, user_id="bob", device_id="bob-phone", body=PublishInput(**publication(count=10)))
    async def request(request_id):
        try:
            async with db.sessions.begin() as s:
                return await claim(s, user_id="alice", device_id="alice-phone", recipient_id="bob", request_id=request_id, now=NOW)
        except DeliveryError as error:
            return error.code
    request_id = str(uuid4())
    retried = await asyncio.gather(*(request(request_id) for _ in range(15)))
    assert all(item == retried[0] for item in retried)
    results = await asyncio.gather(*(request(str(uuid4())) for _ in range(20)))
    keys = [item["one_time"]["id"] for item in results if isinstance(item, dict)]
    assert len(keys) == len(set(keys)) == 9 and 1 not in keys
    assert results.count("recipient_keys_unavailable") == 11


async def test_authenticated_device_loaded_before_replacement_is_rechecked(db):
    # Reproduce the ORM identity-map race: auth loaded an active device, then a
    # different transaction revoked it before the send acquired its user lock.
    async with db.sessions.begin() as s:
        cached = await s.get(Device, "alice-phone")
        async with db.sessions.begin() as other:
            await register_device(other, user_id="alice", device_id="alice-new", secret="a" * 43,
                replace_active=True, service_secret="b" * 43, now=NOW)
        assert cached.active
        with pytest.raises(DeliveryError, match="device_revoked"):
            await accept(s, message(), now=NOW)
        with pytest.raises(DeliveryError, match="device_revoked"):
            await claim(s, user_id="alice", device_id="alice-phone", recipient_id="bob", request_id=str(uuid4()), now=NOW)


async def test_concurrent_deletion_retries_erase_once_and_leave_one_receipt(db):
    secret = secrets.token_urlsafe(32)
    async def erase():
        async with db.sessions.begin() as s:
            return (await request_deletion(s, subject="user_alice", account_id="alice", receipt_secret=secret, service_secret="a"*43, now=NOW)).account_id
    assert set(await asyncio.gather(*(erase() for _ in range(10)))) == {"alice"}
    async with db.sessions() as s:
        assert await s.get(User, "alice") is None
        assert (await s.scalar(select(func.count()).select_from(AccountDeletion))) == 1


async def test_deletion_serializes_with_sends_and_invalidates_cached_devices(db):
    async def erase():
        async with db.sessions.begin() as s:
            await request_deletion(s, subject="user_alice", account_id="alice", receipt_secret=secrets.token_urlsafe(32), service_secret="a"*43, now=NOW)
    async def send():
        try:
            async with db.sessions.begin() as s:
                await accept(s, message(), now=NOW)
        except DeliveryError as error:
            assert error.code in {"recipient_unavailable", "device_revoked"}
    async with db.sessions.begin() as old:
        cached = await old.get(Device, "alice-phone")
        await asyncio.gather(erase(), *(send() for _ in range(12)))
        assert cached.active
        with pytest.raises(DeliveryError):
            await accept(old, message(), now=NOW)
    async with db.sessions() as s:
        assert await s.get(Device, "alice-phone") is None
        assert (await s.scalar(select(func.count()).select_from(PendingMessage))) == 0


async def test_worker_leases_prevent_stale_completion_overwrite(db):
    async with db.sessions.begin() as s:
        await request_deletion(s, subject="user_alice", account_id="alice", receipt_secret=secrets.token_urlsafe(32), service_secret="a"*43, now=NOW)
    started = asyncio.Event(); release = asyncio.Event()
    class SlowProvider:
        async def delete(self, subject):
            started.set(); await release.wait()
            raise RuntimeError("late original worker failure")
    class RecoveredProvider:
        async def delete(self, subject): assert subject == "user_alice"
    first = asyncio.create_task(process_deletions(db, SlowProvider(), now=NOW, limit=1))
    try:
        await asyncio.wait_for(started.wait(), 5)
        second = await process_deletions(db, RecoveredProvider(), now=NOW+timedelta(minutes=3), limit=1)
        assert second["finished"] == 1
    finally:
        release.set()
    assert (await first)["lease_lost"] == 1
    async with db.sessions() as s:
        job = await s.get(AccountDeletion, "alice")
        assert job.subject is None and job.finished_at is not None and job.error_code is None


async def test_unfinished_signup_serializes_with_account_deletion(db):
    subject, account, key = "user_unfinished", str(uuid4()), "q"*43
    receipt = secrets.token_urlsafe(32)
    async def signup():
        async with db.sessions.begin() as s:
            await lock_account_lifecycle(s, subject, key)
            if await deletion_for(s, subject, key):
                return "deletion_pending"
            if not (await s.scalar(select(User).where(User.subject == subject))):
                s.add(User(id=account, subject=subject, username="unfinished", display_name="QA", created_at=NOW))
        return "created"
    async def erase():
        async with db.sessions.begin() as s:
            await request_deletion(s, subject=subject, account_id=account, receipt_secret=receipt, service_secret=key, now=NOW)
        return "deleted"
    results = await asyncio.gather(*(signup() for _ in range(8)), *(erase() for _ in range(8)))
    assert results.count("deleted") == 8
    async with db.sessions() as s:
        assert await s.get(User, account) is None
        assert (await s.scalar(select(func.count()).select_from(AccountDeletion))) == 1


async def test_s2_cached_recipient_acknowledgement_rechecks_committed_replacement(db):
    # Actual API authentication helper returns the active Device into the SAME
    # session identity map before acknowledge acquires its ordered user lock.
    # All credentials/ciphertext are synthetic fixtures, never real messages.
    from vipi.accounts import active_device, credential_hash
    from vipi.delivery import acknowledge
    key, old_secret = "s" * 43, "o" * 43
    envelope = message()
    async with db.sessions.begin() as seed:
        device = await seed.get(Device, "bob-phone")
        device.credential_hash = credential_hash(old_secret, key)
        await accept(seed, envelope, now=NOW)
    async with db.sessions.begin() as authenticated:
        cached = await active_device(authenticated, "bob", "bob-phone", old_secret, service_secret=key)
        assert cached.active
        async with db.sessions.begin() as replacement:
            await register_device(replacement, user_id="bob", device_id="bob-new", secret="n" * 43,
                replace_active=True, service_secret=key, now=NOW)
        assert cached.active  # deliberately stale ORM object; replacement is committed
        async with db.sessions() as observer:
            assert not (await observer.get(Device, "bob-phone")).active
            assert (await observer.get(Device, "bob-new")).active
            item = await observer.get(PendingMessage, envelope.id)
            assert item.state == "identity_changed" and item.ciphertext is None
        try:
            returned = await acknowledge(authenticated, envelope.id, "bob", "bob-phone", now=NOW)
        except DeliveryError as error:
            assert error.code == "device_revoked" and error.status == 401
            assert not cached.active  # under-lock refresh updated the actual cached Device
        else:
            # Baseline may return identity_changed, NOT delivered or a ciphertext.
            pytest.fail("revoked cached device was not rejected; acknowledgement state=" + returned)


async def test_bot_global_budget_and_one_request_per_account_are_atomic(db):
    from test_bot import gateway, response
    from vipi.db import BotPool
    bot = await gateway(db, lambda request: response(), bot_global_monthly_budget_nano_usd=150)
    try:
        async def attempt(user):
            try:
                await bot.reserve_request(user, str(uuid4()), 100)
                return "reserved"
            except DeliveryError as error:
                return error.code
        results = await asyncio.gather(*(attempt(user) for user in ("alice", "bob", "eve") for _ in range(5)))
        assert results.count("reserved") == 1
        async with db.sessions() as session:
            assert (await session.get(BotPool, "2026-10")).reserved_nano_usd == 100
    finally:
        await bot.close()
