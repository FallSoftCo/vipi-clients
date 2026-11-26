"""Real PostgreSQL migration/foreign-key tests, never a retained application DB."""
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError

from conftest import NOW
from vipi.db import Base, MediaBlob, MediaGrant, PendingMessage
from test_media import media_api


def postgres(db):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('Real PostgreSQL migration/locking qualification required')


async def test_upgrade_from_actual_deployed_head_preserves_ciphertext_and_matches_models(db):
    postgres(db)
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    async with db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        def baseline(sync):
            config.attributes['connection'] = sync
            command.upgrade(config, '20261117_05')
        await connection.run_sync(baseline)
        for name in ['alice', 'bob']:
            await connection.execute(text('INSERT INTO users '
                '(id,subject,username,display_name,created_at,cardless_trial_started_at,cardless_trial_ends_at,deleted,suspended) '
                'VALUES (:id,:subject,:id,:id,:now,:now,:now,false,false)'),
                {'id': name, 'subject': 'migration_' + name, 'now': NOW})
        await connection.execute(text('INSERT INTO pending_messages '
            '(id,sender_id,recipient_id,sender_device_id,recipient_device_id,created_at,expires_at,accepted_at,ciphertext,cipher_type,fingerprint,state) '
            'VALUES (:id,:sender,:recipient,:sd,:rd,:now,:expires,:now,:cipher,3,:fingerprint,:state)'),
            {'id':'historical-envelope','sender':'alice','recipient':'bob','sd':'alice-phone','rd':'bob-phone',
             'now':NOW,'expires':NOW+timedelta(hours=72),'cipher':b'opaque historical ciphertext',
             'fingerprint':'a'*64,'state':'accepted'})
    async with db.engine.begin() as connection:
        def upgrade(sync):
            config.attributes['connection'] = sync
            command.upgrade(config, 'head')
            assert compare_metadata(MigrationContext.configure(sync), Base.metadata) == []
        await connection.run_sync(upgrade)
        assert (await connection.execute(text('SELECT version_num FROM alembic_version'))).scalar_one() == '20261126_01'
        assert (await connection.execute(text('SELECT ciphertext FROM pending_messages WHERE id=:id'),
                                        {'id':'historical-envelope'})).scalar_one() == b'opaque historical ciphertext'
        await connection.run_sync(upgrade)
        assert (await connection.execute(text('SELECT count(*) FROM users'))).scalar_one() == 2


async def test_media_fk_atomicity_and_message_delete_cascade(db):
    postgres(db)
    blob = str(uuid4())
    async with db.sessions.begin() as session:
        session.add(MediaBlob(id=blob,owner_id='alice',owner_device_id='alice-phone',ciphertext_bytes=128,
                              ciphertext_sha256='b'*64,state='ready',created_at=NOW,expires_at=NOW+timedelta(hours=72)))
    with pytest.raises(IntegrityError):
        async with db.sessions.begin() as session:
            session.add(MediaGrant(blob_id=blob,message_id='missing',recipient_id='bob',
                                   recipient_device_id='bob-phone',expires_at=NOW+timedelta(hours=72)))
    async with db.sessions.begin() as session:
        session.add(PendingMessage(id='media-envelope',sender_id='alice',recipient_id='bob',
            sender_device_id='alice-phone',recipient_device_id='bob-phone',created_at=NOW,
            expires_at=NOW+timedelta(hours=72),accepted_at=NOW,ciphertext=b'opaque payload',
            cipher_type=3,fingerprint='c'*64,state='accepted'))
        await session.flush()
        session.add(MediaGrant(blob_id=blob,message_id='media-envelope',recipient_id='bob',
                               recipient_device_id='bob-phone',expires_at=NOW+timedelta(hours=72)))
    async with db.sessions.begin() as session:
        await session.execute(delete(PendingMessage).where(PendingMessage.id=='media-envelope'))
    async with db.sessions() as session:
        assert await session.get(MediaGrant,(blob,'media-envelope')) is None
        assert await session.get(MediaBlob,blob) is not None


async def wait_for_actual_lock_wait(db):
    import asyncio
    deadline=asyncio.get_running_loop().time()+3
    while asyncio.get_running_loop().time()<deadline:
        async with db.engine.connect()as connection:
            count=await connection.scalar(text("SELECT count(*) FROM pg_stat_activity "
                "WHERE datname=current_database() AND pid<>pg_backend_pid() AND wait_event_type='Lock'"))
        if count:
            return
        await asyncio.sleep(.01)
    raise AssertionError('Concurrent request did not reach an actual PostgreSQL lock wait')


async def test_committed_send_wins_cancel_without_losing_ciphertext(media_api,db,monkeypatch):
    import asyncio,secrets
    import vipi.media as media
    from test_media import identity
    from test_media import upload,envelope
    postgres(db)
    api,_,settings=media_api
    _,_,ah=await identity(api,'alice');bob,bd,_=await identity(api,'bob')
    ident,_=await upload(api,ah,secrets.token_bytes(4096));message=envelope(bob,bd,[ident])
    reached=asyncio.Event();release=asyncio.Event();original=media.grant_attachments
    async def hold_grant(*args):
        await original(*args);reached.set();await release.wait()
    monkeypatch.setattr(media,'grant_attachments',hold_grant)
    sending=asyncio.create_task(api.post('/v1/messages',headers=ah,json=message))
    await asyncio.wait_for(reached.wait(),3)
    cancelling=asyncio.create_task(api.delete('/v1/media/uploads/'+ident,headers=ah))
    try:await wait_for_actual_lock_wait(db)
    finally:release.set()
    sent,cancelled=await asyncio.wait_for(asyncio.gather(sending,cancelling),5)
    assert sent.status_code==200 and cancelled.status_code==409
    async with db.sessions()as session:
        assert await session.get(MediaGrant,(ident,message['id'])) is not None
    assert media.CiphertextStore(settings.media_storage_path).path(ident).exists()


async def test_committed_cancel_wins_send_atomically(media_api,db,monkeypatch):
    import asyncio,secrets
    import vipi.media as media
    from test_media import identity
    from test_media import upload,envelope
    postgres(db)
    api,_,settings=media_api
    _,_,ah=await identity(api,'alice');bob,bd,_=await identity(api,'bob')
    ident,_=await upload(api,ah,secrets.token_bytes(4096));message=envelope(bob,bd,[ident])
    reached=asyncio.Event();release=asyncio.Event();original=media.cancel_owned_blob
    async def hold_cancel(*args):
        result=await original(*args);reached.set();await release.wait();return result
    monkeypatch.setattr(media,'cancel_owned_blob',hold_cancel)
    cancelling=asyncio.create_task(api.delete('/v1/media/uploads/'+ident,headers=ah))
    await asyncio.wait_for(reached.wait(),3)
    sending=asyncio.create_task(api.post('/v1/messages',headers=ah,json=message))
    try:await wait_for_actual_lock_wait(db)
    finally:release.set()
    cancelled,sent=await asyncio.wait_for(asyncio.gather(cancelling,sending),5)
    assert cancelled.status_code==200 and sent.status_code==404
    async with db.sessions()as session:
        assert await session.get(PendingMessage,message['id']) is None
        assert await session.get(MediaGrant,(ident,message['id'])) is None
    assert not media.CiphertextStore(settings.media_storage_path).path(ident).exists()


async def test_failed_second_attachment_rolls_back_envelope_and_first_grant(media_api,db):
    import secrets
    from test_media import identity
    from test_media import upload,envelope
    postgres(db)
    api,_,_=media_api;_,_,ah=await identity(api,'alice');bob,bd,_=await identity(api,'bob')
    ident,_=await upload(api,ah,secrets.token_bytes(4096),'00000000-0000-4000-8000-000000000001')
    message=envelope(bob,bd,[ident,'ffffffff-ffff-4fff-8fff-ffffffffffff'])
    response=await api.post('/v1/messages',headers=ah,json=message)
    assert response.status_code==404
    async with db.sessions()as session:
        assert await session.get(PendingMessage,message['id']) is None
        assert await session.get(MediaGrant,(ident,message['id'])) is None


async def test_nonempty_media_downgrade_refuses_loss_then_empty_cycle_matches(db):
    postgres(db)
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    # Model parity against a full real migration is qualified above; this unique
    # fixture uses that same current schema, then exercises the real downgrade.
    async with db.engine.begin()as connection:
        def stamp(sync):
            config.attributes['connection']=sync
            command.stamp(config,'head')
        await connection.run_sync(stamp)
    ident=str(uuid4())
    async with db.sessions.begin()as session:
        session.add(MediaBlob(id=ident,owner_id='alice',owner_device_id='alice-phone',
            ciphertext_bytes=256,ciphertext_sha256='d'*64,state='ready',created_at=NOW,
            expires_at=NOW+timedelta(hours=72)))
    with pytest.raises(RuntimeError,match='unsafe downgrade'):
        async with db.engine.begin()as connection:
            def refuse(sync):
                config.attributes['connection']=sync
                command.downgrade(config,'20261119_02')
            await connection.run_sync(refuse)
    async with db.sessions.begin()as session:
        assert await session.get(MediaBlob,ident)is not None
        await session.execute(delete(MediaBlob).where(MediaBlob.id==ident))
    async with db.engine.begin()as connection:
        def cycle(sync):
            config.attributes['connection']=sync
            command.downgrade(config,'20261119_02')
            command.upgrade(config,'head')
            assert compare_metadata(MigrationContext.configure(sync),Base.metadata)==[]
        await connection.run_sync(cycle)


async def test_actual_upload_worker_exit_and_fresh_worker_reconciliation(media_api,db,tmp_path):
    import asyncio
    import hashlib
    import json
    import os
    from pathlib import Path
    import secrets
    import socket
    import subprocess
    import sys
    import httpx
    from sqlalchemy import text
    from vipi.db import MediaBlob
    from vipi.media import CiphertextStore
    from test_media import identity
    from uuid import uuid4
    if db.engine.dialect.name!='postgresql':
        pytest.skip('Worker restart proof requires the isolated PostgreSQL fixture')
    api,_,settings=media_api;_,_,headers=await identity(api,'alice')
    ciphertext=secrets.token_bytes(120_000);ident=str(uuid4())
    body={'id':ident,'ciphertext_bytes':len(ciphertext),'ciphertext_sha256':hashlib.sha256(ciphertext).hexdigest()}
    assert (await api.post('/v1/media/uploads',headers=headers,json=body)).status_code==200
    async with db.sessions() as session:schema=await session.scalar(text('SELECT current_schema()'))
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(16)
    port=listener.getsockname()[1];worker=None
    async def start(crash):
        spec={'database_url':db.engine.url.render_as_string(hide_password=False),'schema':schema,
              'storage':settings.media_storage_path,'fd':listener.fileno(),'crash_after_finalize':crash}
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        log=(tmp_path/('worker-crash.log' if crash else 'worker-restart.log')).open('wb')
        process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('media_worker.py')),json.dumps(spec)],
            pass_fds=(listener.fileno(),),env=env,stdout=log,stderr=subprocess.STDOUT)
        log.close()
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}',timeout=0.4) as client:
            for _ in range(40):
                assert process.poll() is None, 'isolated worker exited before readiness'
                try:
                    if (await client.get('/health/live')).status_code==200:return process
                except httpx.HTTPError:pass
                await asyncio.sleep(0.05)
        process.terminate();await asyncio.to_thread(process.wait,5)
        raise AssertionError('isolated worker never became ready')
    try:
        worker=await start(True)
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}',timeout=5) as client:
            with pytest.raises(httpx.RemoteProtocolError):
                await client.put(f'/v1/media/{ident}/ciphertext',headers=headers,content=ciphertext)
        assert await asyncio.to_thread(worker.wait,5)==87
        assert CiphertextStore(settings.media_storage_path).path(ident).read_bytes()==ciphertext
        async with db.sessions() as session:
            blob=await session.get(MediaBlob,ident)
            assert blob.state=='uploading' and blob.upload_token is not None
        worker=await start(False)
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}',timeout=5) as client:
            result=await client.get(f'/v1/media/uploads/{ident}',headers=headers)
            assert result.status_code==200 and result.json()['state']=='ready'
            assert (await client.put(f'/v1/media/{ident}/ciphertext',headers=headers,content=ciphertext)).json()['state']=='ready'
            assert (await client.get(f'/v1/media/{ident}/ciphertext',headers=headers)).content==ciphertext
        async with db.sessions() as session:
            blob=await session.get(MediaBlob,ident)
            assert blob.state=='ready' and blob.upload_token is None
    finally:
        if worker is not None and worker.poll() is None:
            worker.terminate();await asyncio.to_thread(worker.wait,5)
        listener.close()
