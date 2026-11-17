"""No live URLs: nonzero, disk-backed SQLite restored-copy qualification."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from conftest import NOW
from test_recovery_gate import settings
from test_recovery import recovery_db, evidence
from vipi.db import Database, User, Device, AccountDeletion, BotPool
from vipi.recovery import BoundRecoveryEvidence, reconcile_marked_offline
from vipi.recovery_admission import RecoveryHoldError, mark_restore


def bound(e=None):
    e = e or evidence()
    return BoundRecoveryEvidence.model_validate(dict(reconciliation=e.model_dump(), coverage=[
        dict(domain=d, snapshot_sha256=e.snapshot_sha256, start_at=e.snapshot_at,
             cutoff_at=e.cutoff_at, artifact_sha256=str(i)*64, claimed_complete=True)
        for i,d in enumerate(['deletions','restrictions','billing','spend','requests','eligibility'],1)]))


async def restored_handle(db):
    url=db.engine.url
    await db.close()
    offline=Database(url, offline_recovery=True)
    await mark_restore(offline, snapshot_sha256='a'*64, snapshot_at=NOW-timedelta(days=2), restore_id=str(uuid4()))
    return offline


async def test_nonzero_restore_stays_held_before_and_after_valid_claims(recovery_db):
    offline=await restored_handle(recovery_db)
    ordinary=Database(offline.engine.url)
    try:
        with pytest.raises(RecoveryHoldError): await ordinary.check_admission()
        report=await reconcile_marked_offline(offline,bound(),now=NOW)
        assert report['restore_state']=='HOLD' and report['runtime_gate_installed']
        assert report['unapplied_domains']==['billing','spend','requests']
        assert not report['reopen_authorized'] and not report['native_reenrollment_qualified']
        async with offline.sessions() as s:
            assert await s.get(User,'alice') is None
            assert (await s.get(User,'bob')).suspended
            assert not (await s.get(Device,'bob-phone')).active
            assert (await s.get(BotPool,'2026-10')).reserved_nano_usd==200
        with pytest.raises(RecoveryHoldError): await ordinary.check_admission()
        # The process-level flag remains false; database marker independently gates startup.
        from vipi.api import create_app
        from test_api import TestVerifier
        app=create_app(settings(),database=ordinary,verifier=TestVerifier(),store_providers={})
        with pytest.raises(RecoveryHoldError):
            async with app.router.lifespan_context(app): pytest.fail('unsafe startup')
    finally:
        await ordinary.close();await offline.close()


async def test_conflict_rolls_back_data_but_not_prior_durable_hold(recovery_db):
    offline=await restored_handle(recovery_db)
    try:
        async with offline.sessions.begin() as s:
            s.add(AccountDeletion(account_id='bob',subject_hash='d'*64,receipt_hash='e'*64,
                created_at=NOW,finished_at=NOW,next_attempt_at=NOW,attempts=0))
        e=evidence();e=evidence(deletions=[x.model_dump() for x in e.deletions]+[
            dict(account_id='bob',subject_hash='f'*64,receipt_hash='e'*64,created_at=NOW,finished_at=NOW)])
        with pytest.raises(ValueError,match='conflicting deletion'):
            await reconcile_marked_offline(offline,bound(e),now=NOW)
        async with offline.sessions() as s:
            assert await s.get(User,'alice') is not None
            assert (await s.get(Device,'alice-phone')).active
            assert (await s.execute(text('SELECT state FROM vipi_restore_hold'))).scalar_one()=='HOLD'
    finally: await offline.close()


def test_missing_or_misbound_external_coverage_rejected():
    b=bound().model_dump();b['coverage'].pop()
    with pytest.raises(ValueError):BoundRecoveryEvidence.model_validate(b)
    b=bound().model_dump();b['coverage'][3]['start_at']=NOW
    with pytest.raises(ValueError):BoundRecoveryEvidence.model_validate(b)
    b=bound().model_dump();b['coverage'][3]['claimed_complete']=False
    with pytest.raises(ValueError):BoundRecoveryEvidence.model_validate(b)


async def test_unmarked_normal_db_unchanged_and_malformed_marker_denies(tmp_path):
    db=Database(f'sqlite+aiosqlite:///{tmp_path}/ordinary.sqlite')
    await db.create_for_test();await db.check_admission()
    async with db.engine.begin() as c:
        await c.execute(text('CREATE TABLE vipi_restore_hold (garbage INTEGER)'))
    with pytest.raises(RecoveryHoldError):await db.check_admission()
    await db.close()


@pytest.mark.parametrize('worker',['billing_worker','maintenance','push'])
async def test_workers_refuse_marked_db_without_provider_dispatch(recovery_db,monkeypatch,worker):
    import importlib
    offline=await restored_handle(recovery_db)
    config=settings().model_copy(update={'database_url':str(offline.engine.url)})
    module=importlib.import_module('vipi.'+worker)
    import vipi.config
    monkeypatch.setattr(vipi.config,'Settings',lambda:config)
    if hasattr(module,'Settings'):monkeypatch.setattr(module,'Settings',lambda:config)
    def bomb(*a,**kw):pytest.fail('provider constructed on held restore')
    name={'billing_worker':'providers_for','maintenance':'expire_deletion_receipts','push':'PushProviders'}[worker]
    monkeypatch.setattr(module,name,bomb)
    try:
        with pytest.raises(RecoveryHoldError):await module.main()
    finally:await offline.close()


@pytest.mark.parametrize('conflict',[False,True])
async def test_cli_publish_only_held_copy_and_failed_reconciliation_retains_hold(recovery_db,tmp_path,monkeypatch,conflict):
    # Only capacity admission is mocked: actual fixture copying, fsync, marker,
    # atomic publication, transaction and connection refusal execute on disk.
    import importlib.util, hashlib, json
    from pathlib import Path
    from types import SimpleNamespace
    script=Path(__file__).resolve().parents[2]/'ops/reconcile-recovery.py'
    spec=importlib.util.spec_from_file_location('offline_recovery_cli',script)
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    if conflict:
        async with recovery_db.sessions.begin() as s:
            s.add(AccountDeletion(account_id='alice',subject_hash='d'*64,receipt_hash='e'*64,
                created_at=NOW,finished_at=NOW,next_attempt_at=NOW,attempts=0))
    await recovery_db.close()
    source=tmp_path/'synthetic.sqlite';before=source.read_bytes();assert len(before)<1024**2
    ev=evidence(snapshot_sha256=hashlib.sha256(before).hexdigest())
    supplied=tmp_path/'external.json';supplied.write_text(bound(ev).model_dump_json())
    out=tmp_path/'space ? query # fragment'
    actual=cli.shutil.disk_usage(tmp_path)
    monkeypatch.setattr(cli.shutil,'disk_usage',lambda _:SimpleNamespace(free=9*1024**3))
    args=SimpleNamespace(snapshot=source,evidence=supplied,output=out)
    if conflict:
        with pytest.raises(ValueError,match='conflicting deletion'):await cli.run(args)
    else:await cli.run(args)
    assert source.read_bytes()==before
    assert json.loads((out/'HOLD.json').read_text())['state']=='HOLD'
    assert not (out/'.restoring.sqlite').exists()
    from sqlalchemy.engine import URL
    ordinary=Database(URL.create('sqlite+aiosqlite',database=str(out/'quarantined.sqlite')))
    try:
        with pytest.raises(RecoveryHoldError):await ordinary.check_admission()
    finally:await ordinary.close()
    assert json.loads((out/'receipt.json').read_text())['complete'] is not conflict
    assert sum(p.stat().st_size for p in out.iterdir() if p.is_file())<2*1024**2


async def test_interrupted_copy_retains_intent_and_never_publishes_target(recovery_db,tmp_path,monkeypatch):
    import importlib.util,hashlib,json
    from pathlib import Path
    from types import SimpleNamespace
    spec=importlib.util.spec_from_file_location('interrupted_recovery_cli',Path(__file__).resolve().parents[2]/'ops/reconcile-recovery.py')
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    await recovery_db.close();source=tmp_path/'synthetic.sqlite';before=source.read_bytes()
    supplied=tmp_path/'external.json';supplied.write_text(bound(evidence(snapshot_sha256=hashlib.sha256(before).hexdigest())).model_dump_json())
    monkeypatch.setattr(cli.shutil,'disk_usage',lambda _:SimpleNamespace(free=9*1024**3))
    def interrupted(src,dst):
        dst.write(src.read(16));raise OSError('synthetic interrupted copy')
    monkeypatch.setattr(cli.shutil,'copyfileobj',interrupted)
    out=tmp_path/'failed'
    with pytest.raises(OSError):await cli.run(SimpleNamespace(snapshot=source,evidence=supplied,output=out))
    assert not (out/'quarantined.sqlite').exists()
    assert json.loads((out/'HOLD.json').read_text())['state']=='HOLD'
    assert not json.loads((out/'receipt.json').read_text())['complete']
    assert source.read_bytes()==before
