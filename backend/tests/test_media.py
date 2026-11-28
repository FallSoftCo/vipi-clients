"""HTTP/storage/grant integration with real reference AES-GCM ciphertext.

Native libsignal photo/picker/playback qualification is separate; this suite
does not claim the opaque relay envelope fixture is mobile Signal encryption.
"""

import asyncio
import base64
from datetime import timedelta
import hashlib
import secrets
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select

from conftest import NOW
from test_api import TestVerifier, identity as legacy_identity
from vipi.api import create_app
from vipi.config import Settings
from vipi.db import MediaBlob, MediaCleanup, MediaGrant, PendingMessage, User
from vipi.media import CiphertextStore, drain_cleanup, expire_media


@pytest_asyncio.fixture
async def media_api(db, tmp_path):
    clock = {"now": NOW}
    settings = Settings(
        database_url="sqlite+aiosqlite://",
        workos_client_id="client_fixture",
        workos_issuer="https://api.workos.com",
        service_secret="a" * 43,
        media_enabled=True,
        media_storage_path=str(tmp_path / "opaque"),
        media_max_bytes=512 * 1024,
        media_owner_bytes=1024 * 1024,
    )
    app = create_app(
        settings, database=db, verifier=TestVerifier(), clock=lambda: clock["now"]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://vipi.test"
    ) as client:
        yield client, clock, settings


async def identity(api, name):
    profile, device, headers = await legacy_identity(api, name)
    result = await api.put("/v1/media/capability", headers=headers, json={"version": 1})
    assert result.status_code == 200, result.text
    return profile, device, headers


def seal(clear, key, attachment, part):
    nonce = secrets.token_bytes(12)
    aad = f"vipi-attachment-v1\0{attachment}\0{part}".encode()
    return nonce + AESGCM(key).encrypt(nonce, clear, aad)


async def upload(api, headers, ciphertext, ident=None):
    ident = ident or str(uuid4())
    body = {
        "id": ident,
        "ciphertext_bytes": len(ciphertext),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
    }
    created = await api.post("/v1/media/uploads", headers=headers, json=body)
    assert created.status_code == 200, created.text
    ready = await api.put(
        f"/v1/media/{ident}/ciphertext", headers=headers, content=ciphertext
    )
    assert ready.status_code == 200, ready.text
    return ident, body


def envelope(bob, device, ids):
    return {
        "id": str(uuid4()),
        "recipient_id": bob["id"],
        "recipient_device_id": device,
        "created_at": NOW.isoformat(),
        "cipher_type": 3,
        "ciphertext": base64.b64encode(
            b"opaque existing-Signal-envelope fixture" * 2
        ).decode(),
        "attachment_ids": ids,
    }


async def test_photo_original_thumbnail_opaque_transfer_and_exact_grants(media_api, db):
    api, _, settings = media_api
    alice, _, ah = await identity(api, "alice")
    bob, bd, bh = await identity(api, "bob")
    _, _, eh = await identity(api, "eve")
    attachment = str(uuid4())
    key = AESGCM.generate_key(bit_length=256)
    original = b"controlled-photo-original\0" + bytes(range(256)) * 800
    thumbnail = b"controlled-photo-thumbnail\0" + bytes(range(128)) * 8
    encrypted = [
        seal(original, key, attachment, "original"),
        seal(thumbnail, key, attachment, "thumbnail"),
    ]
    refs = []
    for ciphertext in encrypted:
        ident, _ = await upload(api, ah, ciphertext)
        refs.append(ident)
        assert (
            await api.get(f"/v1/media/{ident}/ciphertext", headers=bh)
        ).status_code == 404
        assert (
            CiphertextStore(settings.media_storage_path).path(ident).read_bytes()
            == ciphertext
        )
        assert original not in ciphertext and key not in ciphertext
    message = envelope(bob, bd, refs)
    assert (await api.post("/v1/messages", headers=ah, json=message)).status_code == 200
    assert (await api.post("/v1/messages", headers=ah, json=message)).status_code == 200
    async with db.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(MediaGrant)) == 2
    downloaded = 0
    for ident, clear, part in zip(
        refs, [original, thumbnail], ["original", "thumbnail"]
    ):
        response = await api.get(f"/v1/media/{ident}/ciphertext", headers=bh)
        assert (
            response.status_code == 200
            and response.headers["cache-control"] == "no-store"
        )
        ciphertext = response.content
        downloaded += len(ciphertext)
        assert (
            AESGCM(key).decrypt(
                ciphertext[:12],
                ciphertext[12:],
                f"vipi-attachment-v1\0{attachment}\0{part}".encode(),
            )
            == clear
        )
        assert (
            await api.get(f"/v1/media/{ident}/ciphertext", headers=eh)
        ).status_code == 404
    assert downloaded == len(original) + len(thumbnail) + 56
    await api.post("/v1/messages/" + message["id"] + "/receipt", headers=bh)
    async with db.sessions() as session:
        assert (await session.get(PendingMessage, message["id"])).ciphertext is None
    assert (
        await api.get(f"/v1/media/{refs[0]}/ciphertext", headers=bh)
    ).status_code == 200


async def test_incomplete_upload_retry_reuses_ciphertext_and_id(media_api):
    api, _, settings = media_api
    _, _, headers = await identity(api, "alice")
    ciphertext = secrets.token_bytes(120_000)
    ident = str(uuid4())
    body = {
        "id": ident,
        "ciphertext_bytes": len(ciphertext),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
    }
    assert (
        await api.post("/v1/media/uploads", headers=headers, json=body)
    ).status_code == 200
    assert (
        await api.put(
            f"/v1/media/{ident}/ciphertext", headers=headers, content=ciphertext[:-1]
        )
    ).status_code == 409
    assert not list(CiphertextStore(settings.media_storage_path).root.glob("*.part"))
    assert (await api.get("/v1/media/uploads/" + ident, headers=headers)).json()[
        "state"
    ] == "uploading"
    assert (
        await api.put(
            f"/v1/media/{ident}/ciphertext", headers=headers, content=ciphertext
        )
    ).json()["state"] == "ready"
    assert (
        await api.put(
            f"/v1/media/{ident}/ciphertext", headers=headers, content=ciphertext
        )
    ).json()["state"] == "ready"
    changed = body | {"ciphertext_sha256": "b" * 64}
    assert (
        await api.post("/v1/media/uploads", headers=headers, json=changed)
    ).status_code == 409


async def test_cancel_before_send_is_idempotent_and_cannot_publish(media_api, db):
    api, _, settings = media_api
    _, _, ah = await identity(api, "alice")
    bob, bd, _ = await identity(api, "bob")
    ident, _ = await upload(api, ah, secrets.token_bytes(4096))
    assert (await api.delete("/v1/media/uploads/" + ident, headers=ah)).json() == {
        "cancelled": True
    }
    assert (await api.delete("/v1/media/uploads/" + ident, headers=ah)).json() == {
        "cancelled": True
    }
    assert not CiphertextStore(settings.media_storage_path).path(ident).exists()
    message = envelope(bob, bd, [ident])
    assert (await api.post("/v1/messages", headers=ah, json=message)).status_code == 404
    async with db.sessions() as session:
        assert await session.get(PendingMessage, message["id"]) is None


async def test_corrupt_upload_and_authenticated_download_failure(media_api):
    api, _, settings = media_api
    _, _, ah = await identity(api, "alice")
    bob, bd, bh = await identity(api, "bob")
    key = AESGCM.generate_key(bit_length=256)
    attachment = str(uuid4())
    clear = b"private original" * 200
    ciphertext = seal(clear, key, attachment, "original")
    ident, _ = await upload(api, ah, ciphertext)
    assert (
        await api.post("/v1/messages", headers=ah, json=envelope(bob, bd, [ident]))
    ).status_code == 200
    path = CiphertextStore(settings.media_storage_path).path(ident)
    corrupt = bytearray(path.read_bytes())
    corrupt[-1] ^= 1
    path.write_bytes(corrupt)
    response = await api.get(f"/v1/media/{ident}/ciphertext", headers=bh)
    assert (
        hashlib.sha256(response.content).hexdigest()
        != hashlib.sha256(ciphertext).hexdigest()
    )
    with pytest.raises(InvalidTag):
        AESGCM(key).decrypt(
            response.content[:12],
            response.content[12:],
            f"vipi-attachment-v1\0{attachment}\0original".encode(),
        )
    with pytest.raises(InvalidTag):
        AESGCM(key).decrypt(
            ciphertext[:12],
            ciphertext[12:-1],
            f"vipi-attachment-v1\0{attachment}\0original".encode(),
        )


async def test_block_and_replacement_never_remap_media_grant(media_api):
    api, _, _ = media_api
    alice, _, ah = await identity(api, "alice")
    bob, bd, bh = await identity(api, "bob")
    ident, _ = await upload(api, ah, secrets.token_bytes(4096))
    message = envelope(bob, bd, [ident])
    assert (await api.post("/v1/messages", headers=ah, json=message)).status_code == 200
    assert (
        await api.put("/v1/blocks/" + alice["id"], headers=bh, json={"blocked": True})
    ).status_code == 200
    assert (
        await api.get(f"/v1/media/{ident}/ciphertext", headers=bh)
    ).status_code == 404
    await api.put("/v1/blocks/" + alice["id"], headers=bh, json={"blocked": False})
    new = str(uuid4())
    secret = secrets.token_urlsafe(32)
    assert (
        await api.post(
            "/v1/devices",
            headers={"Authorization": "Bearer bob"},
            json={"device_id": new, "secret": secret, "replace_active": True},
        )
    ).status_code == 200
    assert (
        await api.get(f"/v1/media/{ident}/ciphertext", headers=bh)
    ).status_code == 401
    new_headers = {
        "Authorization": "Bearer bob",
        "X-Vipi-Device-ID": new,
        "X-Vipi-Device-Secret": secret,
    }
    assert (
        await api.get(f"/v1/media/{ident}/ciphertext", headers=new_headers)
    ).status_code == 404


async def test_expiry_removes_opaque_bytes_and_bounded_authorization(media_api, db):
    api, clock, settings = media_api
    _, _, ah = await identity(api, "alice")
    ident, _ = await upload(api, ah, secrets.token_bytes(4096))
    clock["now"] = NOW + timedelta(hours=73)
    assert (
        await api.get(f"/v1/media/{ident}/ciphertext", headers=ah)
    ).status_code == 404
    async with db.sessions.begin() as session:
        assert (
            await expire_media(
                session, CiphertextStore(settings.media_storage_path), clock["now"]
            )
            == 1
        )
    assert CiphertextStore(settings.media_storage_path).path(ident).exists()
    assert await drain_cleanup(db, CiphertextStore(settings.media_storage_path)) == 1
    assert not CiphertextStore(settings.media_storage_path).path(ident).exists()


async def test_media_disabled_has_no_storage_or_upload_path(db, tmp_path):
    path = tmp_path / "not-created"
    settings = Settings(
        database_url="sqlite+aiosqlite://",
        workos_client_id="client_fixture",
        workos_issuer="https://api.workos.com",
        service_secret="a" * 43,
        media_storage_path=str(path),
    )
    app = create_app(settings, database=db, verifier=TestVerifier(), clock=lambda: NOW)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://vipi.test"
    ) as api:
        _, _, headers = await legacy_identity(api, "alice")
        result = await api.post(
            "/v1/media/uploads",
            headers=headers,
            json={
                "id": str(uuid4()),
                "ciphertext_bytes": 32,
                "ciphertext_sha256": "a" * 64,
            },
        )
        assert result.status_code == 404 and not path.exists()


async def test_reconcile_filesystem_finalize_before_sql_commit_after_worker_loss(
    media_api, db
):
    """Persist exactly the DB/filesystem state left by an abruptly lost worker."""
    api, _, settings = media_api
    _, _, headers = await identity(api, "alice")
    ciphertext = secrets.token_bytes(160_000)
    ident = str(uuid4())
    body = {
        "id": ident,
        "ciphertext_bytes": len(ciphertext),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
    }
    assert (
        await api.post("/v1/media/uploads", headers=headers, json=body)
    ).status_code == 200
    async with db.sessions.begin() as session:
        blob = await session.get(MediaBlob, ident)
        blob.upload_token = str(uuid4())
        blob.lease_until = NOW + timedelta(minutes=15)
    # A process failure leaves finalized ciphertext and an uncommitted ready flag.
    # New normal authenticated status processing must recover without waiting15m.
    store = CiphertextStore(settings.media_storage_path)
    store.path(ident).write_bytes(ciphertext)
    result = await api.get("/v1/media/uploads/" + ident, headers=headers)
    assert result.status_code == 200 and result.json()["state"] == "ready"
    async with db.sessions() as session:
        blob = await session.get(MediaBlob, ident)
        assert (
            blob.state == "ready"
            and blob.upload_token is None
            and blob.lease_until is None
        )
    assert (
        await api.put(
            f"/v1/media/{ident}/ciphertext", headers=headers, content=ciphertext
        )
    ).status_code == 200
    assert store.path(ident).read_bytes() == ciphertext


async def test_recovery_never_promotes_corrupt_or_truncated_finalize(media_api, db):
    api, _, settings = media_api
    _, _, headers = await identity(api, "alice")
    ciphertext = secrets.token_bytes(6000)
    ident = str(uuid4())
    body = {
        "id": ident,
        "ciphertext_bytes": len(ciphertext),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
    }
    assert (
        await api.post("/v1/media/uploads", headers=headers, json=body)
    ).status_code == 200
    path = CiphertextStore(settings.media_storage_path).path(ident)
    for invalid in [ciphertext[:-1], bytes([ciphertext[0] ^ 1]) + ciphertext[1:]]:
        path.write_bytes(invalid)
        assert (await api.get("/v1/media/uploads/" + ident, headers=headers)).json()[
            "state"
        ] == "uploading"
    assert (
        await api.put(
            f"/v1/media/{ident}/ciphertext", headers=headers, content=ciphertext
        )
    ).json()["state"] == "ready"


async def test_account_erasure_commits_cleanup_without_filesystem_side_effects(
    media_api, db, monkeypatch
):
    from vipi.deletion import request_deletion

    api, _, settings = media_api
    alice, _, ah = await identity(api, "alice")
    bob, bd, _ = await identity(api, "bob")
    ident, _ = await upload(api, ah, secrets.token_bytes(4096))
    assert (
        await api.post("/v1/messages", headers=ah, json=envelope(bob, bd, [ident]))
    ).status_code == 200
    store = CiphertextStore(settings.media_storage_path)

    async def erase(session):
        return await request_deletion(
            session,
            subject="user_qa_alice",
            account_id=alice["id"],
            receipt_secret=secret,
            service_secret=settings.service_secret,
            now=NOW,
        )

    secret = secrets.token_urlsafe(32)
    with pytest.raises(RuntimeError, match="transaction interrupted"):
        async with db.sessions.begin() as session:
            await erase(session)
            raise RuntimeError("transaction interrupted")
    async with db.sessions() as session:
        assert await session.get(User, alice["id"]) is not None
        assert await session.get(MediaBlob, ident) is not None
        assert await session.get(MediaCleanup, ident) is None
    assert store.path(ident).exists()
    async with db.sessions.begin() as session:
        await erase(session)
    async with db.sessions() as session:
        assert await session.get(User, alice["id"]) is None
        assert await session.get(User, bob["id"]) is not None
        assert await session.get(MediaBlob, ident) is None
        assert await session.get(MediaCleanup, ident) is not None
        assert await session.scalar(select(func.count()).select_from(MediaGrant)) == 0
    assert store.path(ident).exists()  # durable worker can run after process restart
    original = store.remove

    def unavailable(_):
        raise OSError("isolated storage temporarily unavailable")

    monkeypatch.setattr(store, "remove", unavailable)
    with pytest.raises(OSError):
        await drain_cleanup(db, store)
    async with db.sessions() as session:
        assert await session.get(MediaCleanup, ident) is not None
    monkeypatch.setattr(store, "remove", original)
    assert await drain_cleanup(db, store) == 1
    assert await drain_cleanup(db, store) == 0
    assert not store.path(ident).exists()


async def test_expiry_rollback_preserves_download_and_bytes(media_api, db):
    api, _, settings = media_api
    _, _, headers = await identity(api, "alice")
    ciphertext = secrets.token_bytes(4096)
    ident, _ = await upload(api, headers, ciphertext)
    store = CiphertextStore(settings.media_storage_path)
    with pytest.raises(RuntimeError, match="rollback expiry"):
        async with db.sessions.begin() as session:
            await expire_media(session, store, NOW + timedelta(hours=73))
            raise RuntimeError("rollback expiry")
    assert (
        await api.get(f"/v1/media/{ident}/ciphertext", headers=headers)
    ).content == ciphertext
    assert await drain_cleanup(db, store) == 0
    assert store.path(ident).read_bytes() == ciphertext


async def test_recipient_erasure_revokes_grant_preserves_sender_file(media_api, db):
    from vipi.deletion import request_deletion

    api, _, settings = media_api
    _, _, ah = await identity(api, "alice")
    bob, bd, _ = await identity(api, "bob")
    ident, _ = await upload(api, ah, secrets.token_bytes(4096))
    assert (
        await api.post("/v1/messages", headers=ah, json=envelope(bob, bd, [ident]))
    ).status_code == 200
    async with db.sessions.begin() as session:
        await request_deletion(
            session,
            subject="user_qa_bob",
            account_id=bob["id"],
            receipt_secret=secrets.token_urlsafe(32),
            service_secret=settings.service_secret,
            now=NOW,
        )
    assert (
        await api.get(f"/v1/media/{ident}/ciphertext", headers=ah)
    ).status_code == 200
    assert await drain_cleanup(db, CiphertextStore(settings.media_storage_path)) == 0
    async with db.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(MediaGrant)) == 0


async def test_stalled_body_times_out_releases_lease_and_removes_partial(media_api, db):
    api, _, settings = media_api
    _, _, headers = await identity(api, "alice")
    settings.media_upload_timeout_seconds = 0.05
    ident = str(uuid4())
    ciphertext = secrets.token_bytes(4096)
    body = {
        "id": ident,
        "ciphertext_bytes": len(ciphertext),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
    }
    assert (
        await api.post("/v1/media/uploads", headers=headers, json=body)
    ).status_code == 200

    async def stalled():
        yield ciphertext[:512]
        await asyncio.Event().wait()

    response = await asyncio.wait_for(
        api.put(f"/v1/media/{ident}/ciphertext", headers=headers, content=stalled()), 2
    )
    assert response.status_code == 408
    async with db.sessions() as session:
        blob = await session.get(MediaBlob, ident)
        assert (
            blob.state == "uploading"
            and blob.upload_token is None
            and blob.lease_until is None
        )
    assert not list(CiphertextStore(settings.media_storage_path).root.glob("*.part"))
    assert (
        await api.put(
            f"/v1/media/{ident}/ciphertext", headers=headers, content=ciphertext
        )
    ).status_code == 200


async def test_delayed_send_keeps_blob_for_entire_envelope_lifetime(media_api, db):
    api, clock, settings = media_api
    _, _, ah = await identity(api, "alice")
    bob, bd, bh = await identity(api, "bob")
    ident, _ = await upload(api, ah, secrets.token_bytes(4096))
    clock["now"] = NOW + timedelta(hours=71)
    message = envelope(bob, bd, [ident])
    message["created_at"] = clock["now"].isoformat()
    assert (await api.post("/v1/messages", headers=ah, json=message)).status_code == 200
    clock["now"] = NOW + timedelta(hours=73)
    async with db.sessions.begin() as session:
        assert (
            await expire_media(
                session, CiphertextStore(settings.media_storage_path), clock["now"]
            )
            == 0
        )
        blob = await session.get(MediaBlob, ident)
        grant = await session.get(MediaGrant, (ident, message["id"]))
        from vipi.delivery import utc

        assert (
            utc(blob.expires_at) == utc(grant.expires_at) == NOW + timedelta(hours=143)
        )
    assert await drain_cleanup(db, CiphertextStore(settings.media_storage_path)) == 0
    assert (
        await api.get(f"/v1/media/{ident}/ciphertext", headers=bh)
    ).status_code == 200


async def test_old_device_can_text_but_must_advertise_attachments(media_api):
    api, _, _ = media_api
    _, _, sender = await identity(api, "alice")
    bob, device_id, recipient = await legacy_identity(api, "bob")
    path = f"/v1/media/capability/{bob['id']}"
    assert (await api.get(path, headers=sender)).json() == {
        "version": 0,
        "device_id": device_id,
    }
    assert (await api.get(path)).status_code == 401
    blob_id, _ = await upload(api, sender, secrets.token_bytes(128))
    media_message = envelope(bob, device_id, [blob_id])
    failure = await api.post("/v1/messages", headers=sender, json=media_message)
    assert (
        failure.status_code == 409
        and failure.json()["error"] == "recipient_media_unsupported"
    )
    assert (
        await api.get(f"/v1/media/{blob_id}/ciphertext", headers=recipient)
    ).status_code == 404
    assert (
        await api.post(
            "/v1/messages", headers=sender, json=envelope(bob, device_id, [])
        )
    ).status_code == 200
    for _ in range(2):
        result = await api.put(
            "/v1/media/capability", headers=recipient, json={"version": 1}
        )
        assert result.json() == {"version": 1}
    assert (await api.get(path, headers=sender)).json() == {
        "version": 1,
        "device_id": device_id,
    }
    assert (
        await api.post("/v1/messages", headers=sender, json=media_message)
    ).status_code == 200
    assert (
        await api.put("/v1/media/capability", headers=recipient, json={"version": 8})
    ).status_code == 422


async def test_account_deletion_and_expiry_owner_complete_shared_feature_cleanup(
    media_api, db, monkeypatch
):
    from test_groups_api import create, invite_join
    from vipi import maintenance

    _, _, base_settings = media_api
    settings = base_settings.model_copy(
        update={"groups_enabled": True, "account_deletion_enabled": True}
    )
    app = create_app(settings, database=db, verifier=TestVerifier(), clock=lambda: NOW)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://vipi.test"
    ) as api:
        alice, _, ah = await identity(api, "alice")
        bob, bd, bh = await identity(api, "bob")
        group = await create(api, ah)
        await invite_join(api, group, ah, bob, bh)
        blob, _ = await upload(api, ah, secrets.token_bytes(2048))
        peer_blob, _ = await upload(api, bh, secrets.token_bytes(2048))
        assert (
            await api.post("/v1/messages", headers=ah, json=envelope(bob, bd, [blob]))
        ).status_code == 200
        assert (
            await api.get(f"/v1/media/{blob}/ciphertext", headers=bh)
        ).status_code == 200
        body = {"account_id": alice["id"], "receipt_secret": secrets.token_urlsafe(32)}
        for _ in range(2):
            response = await api.request("DELETE", "/v1/me", headers=ah, json=body)
            assert (
                response.status_code == 202 and response.json()["status"] == "deleted"
            )
        assert (
            await api.get(f"/v1/media/{blob}/ciphertext", headers=bh)
        ).status_code == 404
        remaining = await api.get("/v1/groups/" + group["id"], headers=bh)
        assert {m["user_id"] for m in remaining.json()["members"]} == {bob["id"]}

    store = CiphertextStore(settings.media_storage_path)
    assert store.path(blob).is_file() and store.path(peer_blob).is_file()
    # Keep the clock consistent with the API and use the same isolated test schema.
    from datetime import datetime

    class FixtureTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(maintenance, "datetime", FixtureTime)
    monkeypatch.setattr(maintenance, "Settings", lambda: settings)
    monkeypatch.setattr(maintenance, "Database", lambda _: db)
    await maintenance.main()
    assert not store.path(blob).exists() and store.path(peer_blob).is_file()
    async with db.sessions() as s:
        assert await s.get(MediaCleanup, blob) is None
        assert await s.get(MediaBlob, peer_blob) is not None
