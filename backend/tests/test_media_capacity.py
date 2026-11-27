"""Shared admission on the existing schema and real portal/worker boundaries."""

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import timedelta
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from test_media import identity, media_api, seal
from vipi.db import MediaBlob, MediaCleanup
from vipi.media import CiphertextStore, drain_cleanup


def attachment(size=16384):
    ident = str(uuid4())
    body = seal(
        secrets.token_bytes(size - 28), secrets.token_bytes(32), ident, "original"
    )
    return body, {
        "id": ident,
        "ciphertext_sha256": hashlib.sha256(body).hexdigest(),
        "ciphertext_bytes": len(body),
    }


@asynccontextmanager
async def live_worker(db, settings, tmp, limit, objects):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    async with db.sessions() as session:
        schema = await session.scalar(text("select current_schema()"))
    spec = {
        "database_url": db.engine.url.render_as_string(hide_password=False),
        "schema": schema,
        "storage": settings.media_storage_path,
        "fd": listener.fileno(),
        "crash_after_finalize": False,
        "global_bytes": limit,
        "global_blobs": objects,
    }
    module = Path(__file__).with_name("media_worker.py")
    try:
        with (tmp / ("worker-" + str(listener.getsockname()[1]) + ".log")).open(
            "wb"
        ) as log:
            child = subprocess.Popen(
                [sys.executable, str(module), json.dumps(spec)],
                pass_fds=(listener.fileno(),),
                env=dict(os.environ, PYTHONPATH=str(module.parents[1])),
                stdout=log,
                stderr=log,
            )
        try:
            async with httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{listener.getsockname()[1]}", timeout=10
            ) as client:
                for _ in range(100):
                    assert child.poll() is None
                    try:
                        if (
                            await client.get("/health/live", timeout=0.3)
                        ).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.05)
                else:
                    pytest.fail("worker readiness timed out")
                yield client, child
        finally:
            child.terminate()
            await asyncio.to_thread(child.wait, 10)
    finally:
        listener.close()


@pytest.mark.parametrize(("byte_cap", "object_cap"), [(16384, 8), (65536, 1)])
async def test_two_processes_share_admission_and_exact_ciphertext(
    media_api, db, tmp_path, byte_cap, object_cap
):
    if db.engine.dialect.name != "postgresql":
        pytest.skip("Cross-process PostgreSQL test")
    setup, _, settings = media_api
    headers = [(await identity(setup, name))[2] for name in ("alice", "bob")]
    payloads = [attachment(), attachment()]
    async with AsyncExitStack() as stack:
        roles = [
            await stack.enter_async_context(
                live_worker(db, settings, tmp_path, byte_cap, object_cap)
            )
            for _ in headers
        ]
        workers = [client for client, _ in roles]

        async def reserve(index):
            return await workers[index].post(
                "/v1/media/uploads", headers=headers[index], json=payloads[index][1]
            )

        replies = await asyncio.gather(reserve(0), reserve(1))
        assert sorted(r.status_code for r in replies) == [200, 429]
        winner = next(i for i, r in enumerate(replies) if r.status_code == 200)
        loser = 1 - winner
        assert replies[loser].json()["error"] == "media_storage_full"
        for index in (winner, loser):
            # An original reservation retry does not consume a second slot.
            assert (await reserve(index)).status_code == 200
            body, declaration = payloads[index]
            route = "/v1/media/" + declaration["id"] + "/ciphertext"
            cross_worker = workers[1 - index]
            put = await cross_worker.put(route, headers=headers[index], content=body)
            assert put.status_code == 200, put.text
            assert (
                await workers[index].get(route, headers=headers[index])
            ).content == body
            assert (
                await workers[index].delete(
                    "/v1/media/uploads/" + declaration["id"], headers=headers[index]
                )
            ).status_code == 200


async def test_reading_deleted_owner_keeps_disk_charge_until_fd_close(media_api, db):
    from vipi.deletion import request_deletion
    from conftest import NOW

    api, _, settings = media_api
    owner, _, ah = await identity(api, "alice")
    _, _, bh = await identity(api, "bob")
    body, original = attachment()
    settings.media_global_bytes = len(body)
    assert (
        await api.post("/v1/media/uploads", headers=ah, json=original)
    ).status_code == 200
    ident = original["id"]
    assert (
        await api.put(f"/v1/media/{ident}/ciphertext", headers=ah, content=body)
    ).status_code == 200
    store = CiphertextStore(settings.media_storage_path)
    _, other = attachment()
    # Same kernel shared lock used by the real download descriptor.
    with store.path(ident).open("rb") as reader:
        fcntl.flock(reader, fcntl.LOCK_SH)
        async with db.sessions.begin() as session:
            await request_deletion(
                session,
                subject="user_qa_alice",
                account_id=owner["id"],
                receipt_secret=secrets.token_urlsafe(32),
                service_secret=settings.service_secret,
                now=NOW,
            )
        assert await drain_cleanup(db, store) == 0
        assert reader.read() == body
        assert (
            await api.post("/v1/media/uploads", headers=bh, json=other)
        ).status_code == 429
        async with db.sessions() as session:
            assert await session.get(MediaBlob, ident) is None
            assert await session.get(MediaCleanup, ident) is not None
    assert await drain_cleanup(db, store) == 1
    assert (
        await api.post("/v1/media/uploads", headers=bh, json=other)
    ).status_code == 200


async def test_disk_floor_rechecked_before_body_and_on_legacy_retry(
    media_api, db, monkeypatch
):
    api, _, settings = media_api
    _, _, headers = await identity(api, "alice")
    body, record = attachment()
    route = "/v1/media/" + record["id"] + "/ciphertext"
    floor = settings.media_min_free_bytes
    settings.media_min_free_bytes = 1 << 62
    assert (
        await api.post("/v1/media/uploads", headers=headers, json=record)
    ).status_code == 507
    settings.media_min_free_bytes = floor
    assert (
        await api.post("/v1/media/uploads", headers=headers, json=record)
    ).status_code == 200
    inode_floor = settings.media_min_free_inodes
    settings.media_min_free_inodes = 1 << 62

    async def untouched():
        pytest.fail("must refuse before receiving any ciphertext")
        yield body

    assert (
        await api.put(route, headers=headers, content=untouched())
    ).status_code == 507
    settings.media_min_free_inodes = inode_floor

    def no_allocation(*_):
        raise OSError(errno.ENOSPC, "full fixture")

    with monkeypatch.context() as patch:
        patch.setattr(os, "posix_fallocate", no_allocation)
        assert (
            await api.put(route, headers=headers, content=untouched())
        ).status_code == 507
    store = CiphertextStore(settings.media_storage_path)
    assert not list(store.root.glob("*.part"))
    # A legacy interrupted worker may leave a token-named partial on disk.
    stale = store.temporary(record["id"], str(uuid4()))
    stale.write_bytes(body[:123])
    assert (await api.put(route, headers=headers, content=body)).status_code == 200
    assert not stale.exists()
    assert (await api.get(route, headers=headers)).content == body


async def test_partial_put_stays_charged_through_concurrent_cancellation(media_api, db):
    api, _, settings = media_api
    _, _, ah = await identity(api, "alice")
    _, _, bh = await identity(api, "bob")
    body, record = attachment()
    _, other = attachment()
    settings.media_global_bytes = len(body)
    assert (
        await api.post("/v1/media/uploads", headers=ah, json=record)
    ).status_code == 200
    half_written, resume = asyncio.Event(), asyncio.Event()

    async def paced_body():
        yield body[: len(body) // 2]
        half_written.set()
        await resume.wait()
        yield body[len(body) // 2 :]

    ident = record["id"]
    put = asyncio.create_task(
        api.put(f"/v1/media/{ident}/ciphertext", headers=ah, content=paced_body())
    )
    try:
        await asyncio.wait_for(half_written.wait(), 5)
        store = CiphertextStore(settings.media_storage_path)
        (partial,) = store.root.glob("*.part")
        assert partial.stat().st_blocks * 512 >= len(body)
        cancelled = await api.delete("/v1/media/uploads/" + ident, headers=ah)
        assert cancelled.status_code == 200
        assert (
            await api.post("/v1/media/uploads", headers=bh, json=other)
        ).status_code == 429
    finally:
        resume.set()
        response = await put
    assert response.status_code == 404
    assert not list(store.root.glob("*.part"))
    assert await drain_cleanup(db, store) == 1
    assert (
        await api.post("/v1/media/uploads", headers=bh, json=other)
    ).status_code == 200


async def test_killed_partial_worker_preserves_charge_and_exact_retry(
    media_api, db, tmp_path
):
    if db.engine.dialect.name != "postgresql":
        pytest.skip("Cross-process PostgreSQL test")
    from conftest import NOW

    setup, _, settings = media_api
    _, _, ah = await identity(setup, "alice")
    _, _, bh = await identity(setup, "bob")
    body, original = attachment(65536)
    _, other = attachment()
    ident = original["id"]
    route = "/v1/media/" + ident + "/ciphertext"
    store = CiphertextStore(settings.media_storage_path)
    async with AsyncExitStack() as stack:
        first, process = await stack.enter_async_context(
            live_worker(db, settings, tmp_path, len(body), 8)
        )
        second, _ = await stack.enter_async_context(
            live_worker(db, settings, tmp_path, len(body), 8)
        )
        assert (
            await first.post("/v1/media/uploads", headers=ah, json=original)
        ).status_code == 200
        resume = asyncio.Event()

        async def unfinished():
            yield body[:8192]
            await resume.wait()
            yield body[8192:]

        sending = asyncio.create_task(
            first.put(route, headers=ah, content=unfinished())
        )
        try:
            for _ in range(100):
                async with db.sessions() as session:
                    blob = await session.get(MediaBlob, ident)
                    if (
                        blob.upload_token
                        and store.temporary(ident, blob.upload_token).exists()
                    ):
                        break
                await asyncio.sleep(0.025)
            else:
                pytest.fail("First writer never took its durable lease")
            process.kill()
            await asyncio.to_thread(process.wait, 5)
        finally:
            resume.set()
            with pytest.raises(httpx.HTTPError):
                await sending
        assert len(list(store.root.glob("*.part"))) == 1
        assert (
            await second.post("/v1/media/uploads", headers=bh, json=other)
        ).status_code == 429
        assert (await second.put(route, headers=ah, content=body)).status_code == 409
        # Advance only the isolated record beyond the original 15-minute lease.
        async with db.sessions.begin() as session:
            blob = await session.get(MediaBlob, ident, with_for_update=True)
            blob.lease_until = NOW - timedelta(seconds=1)
        assert (await second.put(route, headers=ah, content=body)).status_code == 200
        assert (await second.get(route, headers=ah)).content == body
        assert not list(store.root.glob("*.part"))


async def test_wrong_or_missing_volume_never_discharges_cleanup(
    media_api, db, tmp_path
):
    from conftest import NOW
    from vipi.delivery import DeliveryError

    api, _, settings = media_api
    _, _, headers = await identity(api, "alice")
    body, record = attachment()
    ident = record["id"]
    assert (
        await api.post("/v1/media/uploads", headers=headers, json=record)
    ).status_code == 200
    assert (
        await api.put(f"/v1/media/{ident}/ciphertext", headers=headers, content=body)
    ).status_code == 200
    path = Path(settings.media_storage_path)
    marker = path / ".vipi-volume-id"
    expected = str(uuid4())
    with pytest.raises(DeliveryError):
        CiphertextStore(path, require_existing=True, volume_id=expected)
    marker.write_text(expected + "\n")
    store = CiphertextStore(path, require_existing=True, volume_id=expected)
    async with db.sessions.begin() as session:
        blob = await session.get(MediaBlob, ident, with_for_update=True)
        blob.state = "cancelled"
        session.add(MediaCleanup(blob_id=ident, created_at=NOW))
    original = tmp_path / "original-disk"
    path.rename(original)
    path.mkdir()
    with pytest.raises(DeliveryError):
        await drain_cleanup(db, store)
    with pytest.raises(DeliveryError):
        CiphertextStore(path, require_existing=True, volume_id=expected)
    async with db.sessions() as session:
        assert await session.get(MediaCleanup, ident) is not None
    assert (original / (ident + ".ciphertext")).read_bytes() == body
    path.rmdir()
    original.rename(path)
    assert await drain_cleanup(db, store) == 1


async def test_filesystem_without_preallocation_fails_before_reading(
    media_api, monkeypatch
):
    api, _, _ = media_api
    _, _, headers = await identity(api, "alice")
    _, record = attachment()
    assert (
        await api.post("/v1/media/uploads", headers=headers, json=record)
    ).status_code == 200
    monkeypatch.delattr(os, "posix_fallocate", raising=False)

    async def untouched():
        pytest.fail("unsupported storage must not read a request body")
        yield b""

    response = await api.put(
        "/v1/media/" + record["id"] + "/ciphertext",
        headers=headers,
        content=untouched(),
    )
    assert response.status_code == 507
