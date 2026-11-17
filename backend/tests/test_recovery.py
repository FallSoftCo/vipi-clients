"""Synthetic, disk-backed recovery copies only; no provider or production DB."""
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import select

from conftest import NOW
from vipi.db import (AccountDeletion, BotPool, Database, Device, Entitlement,
                     Reservation, UsageBucket, User)
from vipi.recovery import RecoveryEvidence, reconcile_offline
from vipi.accounts import active_device, register_device
from vipi.delivery import DeliveryError


@pytest.fixture
async def recovery_db(tmp_path):
    # Intentionally do not reuse conftest.db: that fixture may use an environment
    # PostgreSQL URL. This suite never reads that variable or connects to it.
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/synthetic.sqlite")
    await db.create_for_test()
    async with db.sessions.begin() as s:
        for uid in ("alice", "bob", "eve"):
            s.add(User(id=uid, subject="user_" + uid, username=uid, display_name=uid, created_at=NOW))
        await s.flush()
        for uid in ("alice", "bob", "eve"):
            s.add(Device(id=uid+"-phone", user_id=uid, credential_hash="a"*64, active=True, created_at=NOW))
        s.add(Entitlement(id="grant", user_id="bob", product="bot", store="apple", transaction_id="tx",
            expires_at=NOW+timedelta(days=30), verified_at=NOW, environment="Production", lease_token="old", lease_until=NOW+timedelta(minutes=1)))
        s.add(BotPool(period="2026-10", budget_nano_usd=1000, reserved_nano_usd=200, spent_nano_usd=400))
        s.add(UsageBucket(user_id="bob", period="2026-10", budget_nano_usd=900, reserved_nano_usd=200, spent_nano_usd=300))
        s.add(Reservation(id="already-dispatched", user_id="bob", period="2026-10", reserved_nano_usd=200,
            state="uncertain", created_at=NOW))
    yield db
    await db.close()


def evidence(**changes):
    value = dict(schema_version=1, snapshot_sha256="a"*64,
        snapshot_at=NOW-timedelta(days=2), cutoff_at=NOW, claimed_complete=True,
        deletions=[dict(account_id="alice", subject_hash="b"*64, receipt_hash="c"*64,
            subject=None, created_at=NOW-timedelta(days=1), finished_at=NOW)],
        restrictions=[dict(account_id="bob", suspended=True, observed_at=NOW)])
    value.update(changes)
    return RecoveryEvidence.model_validate(value)


async def test_quarantine_deletion_restriction_and_spend_are_idempotent(recovery_db):
    for _ in range(2):
        report = await reconcile_offline(recovery_db, evidence(), snapshot_sha256="a"*64, now=NOW)
        assert report['claimed_complete'] is True
        assert not report['authority_verified'] and not report['interval_complete_verified']
        assert not report['reopen_authorized'] and not report['bot_dispatch_authorized']
        assert not report['runtime_gate_installed']
    async with recovery_db.sessions() as s:
        assert await s.get(User, "alice") is None
        assert await s.get(Device, "alice-phone") is None
        assert (await s.get(AccountDeletion, "alice")).receipt_hash == "c"*64
        assert (await s.get(User, "bob")).suspended
        assert not (await s.get(User, "eve")).suspended
        assert not any(x.active for x in (await s.execute(select(Device))).scalars())
        grant = await s.get(Entitlement, "grant")
        assert grant.verified_at is None and grant.lease_token is None and grant.lease_until is None
        pool = await s.get(BotPool, "2026-10")
        assert (pool.reserved_nano_usd, pool.spent_nano_usd) == (200, 400)
        bucket = await s.get(UsageBucket, ("bob", "2026-10"))
        assert (bucket.reserved_nano_usd, bucket.spent_nano_usd) == (200, 300)
        assert (await s.get(Reservation, "already-dispatched")).state == "uncertain"


async def test_conflicting_late_record_rolls_back_entire_transaction(recovery_db):
    async with recovery_db.sessions.begin() as s:
        s.add(AccountDeletion(account_id="bob", subject_hash="d"*64, receipt_hash="e"*64,
            subject=None, created_at=NOW, finished_at=NOW, next_attempt_at=NOW, attempts=0))
    ev = evidence()
    ev = evidence(deletions=[x.model_dump() for x in ev.deletions] + [dict(account_id="bob",
        subject_hash="f"*64, receipt_hash="e"*64, created_at=NOW, finished_at=NOW)])
    with pytest.raises(ValueError, match="conflicting deletion"):
        await reconcile_offline(recovery_db, ev, snapshot_sha256="a"*64, now=NOW)
    async with recovery_db.sessions() as s:
        assert await s.get(User, "alice") is not None
        assert (await s.get(Device, "alice-phone")).active
        assert (await s.get(Entitlement, "grant")).verified_at is not None


async def test_untrusted_restore_cannot_clear_restriction_or_completed_deletion(recovery_db):
    await reconcile_offline(recovery_db, evidence(), snapshot_sha256="a"*64, now=NOW)
    ev = evidence(claimed_complete=False, deletions=[dict(account_id="alice", subject_hash="b"*64,
        receipt_hash="c"*64, subject="user_alice", created_at=NOW)],
        restrictions=[dict(account_id="bob", suspended=False, observed_at=NOW)])
    result = await reconcile_offline(recovery_db, ev, snapshot_sha256="a"*64, now=NOW)
    assert result['counts']['restore_requests_not_applied'] == 1
    async with recovery_db.sessions() as s:
        assert (await s.get(User, "bob")).suspended
        old = await s.get(AccountDeletion, "alice")
        assert old.finished_at is not None and old.subject is None


async def test_stale_snapshot_binding_future_cutoff_and_duplicate_evidence_rejected(recovery_db):
    with pytest.raises(ValueError):
        await reconcile_offline(recovery_db, evidence(), snapshot_sha256="d"*64, now=NOW)
    with pytest.raises(ValueError):
        await reconcile_offline(recovery_db, evidence(cutoff_at=NOW+timedelta(days=1)), snapshot_sha256="a"*64, now=NOW)
    with pytest.raises(ValueError):
        evidence(restrictions=[dict(account_id="bob", suspended=True, observed_at=NOW)]*2)
    with pytest.raises(ValueError):
        evidence(cutoff_at=NOW-timedelta(days=1))
    async with recovery_db.sessions() as s:
        assert (await s.get(Device, "alice-phone")).active


async def test_old_device_stays_invalid_and_spend_request_stays_consumed(recovery_db):
    from vipi.budget import reserve, BudgetError
    await reconcile_offline(recovery_db, evidence(deletions=[], restrictions=[]), snapshot_sha256="a"*64, now=NOW)
    async with recovery_db.sessions.begin() as s:
        with pytest.raises(DeliveryError):
            await register_device(s, user_id="bob", device_id="bob-phone", secret="x"*43,
                replace_active=True, service_secret="synthetic-key", now=NOW)
        with pytest.raises(BudgetError, match="request_already_used"):
            await reserve(s, user_id="bob", request_id="already-dispatched", maximum_cost=1, now=NOW)
    # No assertion about unknown post-snapshot IDs: that absent authority remains
    # a blocker, not a magically reconstructed idempotency ledger.


async def test_cli_copies_only_synthetic_snapshot_and_never_reopens(recovery_db, tmp_path):
    import shutil
    if shutil.disk_usage(tmp_path).free < 8 * 1024**3 + 16 * 1024**2:
        pytest.skip("real CLI 8 GiB admission floor unavailable")
    await recovery_db.close()
    source = tmp_path/'synthetic.sqlite'
    before = source.read_bytes()
    ev = evidence(snapshot_sha256=hashlib.sha256(before).hexdigest())
    from test_restore_admission import bound
    supplied = tmp_path/'evidence.json'; supplied.write_text(bound(ev).model_dump_json())
    out = tmp_path/'result'
    script = Path(__file__).resolve().parents[2]/'ops/reconcile-recovery.py'
    result = subprocess.run([sys.executable, str(script), '--snapshot', str(source),
        '--evidence', str(supplied), '--output', str(out)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert source.read_bytes() == before
    assert not json.loads((out/'report.json').read_text())['reopen_authorized']
    assert json.loads((out/'receipt.json').read_text())['source_unchanged']
    again = subprocess.run([sys.executable, str(script), '--snapshot', str(source),
        '--evidence', str(supplied), '--output', str(out)], capture_output=True, text=True, timeout=30)
    assert again.returncode != 0
    assert json.loads((out/'receipt.json').read_text())['complete']


async def test_deleted_personal_spend_does_not_release_global_reserve(recovery_db):
    ev = evidence(deletions=[dict(account_id="bob", subject_hash="d"*64, receipt_hash="e"*64,
        created_at=NOW, finished_at=NOW)], restrictions=[])
    await reconcile_offline(recovery_db, ev, snapshot_sha256="a"*64, now=NOW)
    async with recovery_db.sessions() as s:
        assert await s.get(Reservation, "already-dispatched") is None
        assert await s.get(UsageBucket, ("bob", "2026-10")) is None
        pool = await s.get(BotPool, "2026-10")
        assert (pool.reserved_nano_usd, pool.spent_nano_usd) == (200, 400)


async def test_excluded_transport_rows_cannot_survive_wrong_snapshot_exclusions(recovery_db):
    from vipi.db import PendingMessage, PushToken
    from test_delivery import message
    from vipi.delivery import accept
    async with recovery_db.sessions.begin() as s:
        await accept(s, message(), now=NOW)
    report = await reconcile_offline(recovery_db, evidence(deletions=[], restrictions=[]), snapshot_sha256="a"*64, now=NOW)
    async with recovery_db.sessions() as s:
        assert not (await s.execute(select(PendingMessage))).scalars().all()
    assert report['services_must_remain_stopped']


async def test_cli_special_path_characters_address_only_exact_output(recovery_db, tmp_path):
    import shutil
    if shutil.disk_usage(tmp_path).free < 8 * 1024**3 + 16 * 1024**2:
        pytest.skip("real CLI 8 GiB admission floor unavailable")
    import sqlite3
    await recovery_db.close()
    source = tmp_path / 'synthetic.sqlite'
    before = source.read_bytes()
    supplied = tmp_path / 'special-evidence.json'
    from test_restore_admission import bound
    supplied.write_text(bound(evidence(snapshot_sha256=hashlib.sha256(before).hexdigest())).model_dump_json())
    out = tmp_path / 'space ? query # fragment'
    before_files = {p.relative_to(tmp_path) for p in tmp_path.rglob('*') if p.is_file()}
    script = Path(__file__).resolve().parents[2] / 'ops/reconcile-recovery.py'
    result = subprocess.run([sys.executable, str(script), '--snapshot', str(source),
        '--evidence', str(supplied), '--output', str(out)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert source.read_bytes() == before
    exact = out / 'quarantined.sqlite'
    with sqlite3.connect(exact.resolve().as_uri() + '?mode=ro', uri=True) as db:
        assert db.execute('SELECT count(*) FROM users WHERE id=?', ('alice',)).fetchone() == (0,)
        assert db.execute('SELECT count(*) FROM devices WHERE active').fetchone() == (0,)
        assert db.execute('SELECT verified_at FROM entitlements WHERE id=?', ('grant',)).fetchone() == (None,)
    after_files = {p.relative_to(tmp_path) for p in tmp_path.rglob('*') if p.is_file()}
    assert after_files - before_files == {
        (out / name).relative_to(tmp_path) for name in ('quarantined.sqlite', 'report.json', 'receipt.json', 'HOLD.json')}
    receipt = json.loads((out / 'receipt.json').read_text())
    assert receipt['output_sha256'] == hashlib.sha256(exact.read_bytes()).hexdigest()
    assert receipt['source_unchanged'] and receipt['complete']
