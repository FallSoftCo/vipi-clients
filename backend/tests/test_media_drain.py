"""Reconcile a media admission through restart, full disable, and drain-only service."""

from hashlib import sha256
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from conftest import NOW
from test_api import TestVerifier
from test_media import envelope, identity, media_api, seal, upload
from vipi.api import create_app
from vipi.config import Settings
from vipi.db import MediaBlob, MediaGrant, PendingMessage


def test_conflicting_media_drain_configuration_is_rejected():
    with pytest.raises(ValidationError, match="Media drain requires"):
        Settings(
            database_url="sqlite+aiosqlite://",
            workos_client_id="client_fixture",
            workos_issuer="https://fixture.invalid",
            service_secret="x" * 43,
            media_draining=True,
            media_enabled=False,
        )


async def test_admitted_media_remains_readable_and_new_admission_is_closed(
    media_api, db
):
    api, _, settings = media_api
    _, _, sender = await identity(api, "alice")
    bob, bob_device, recipient = await identity(api, "bob")
    _, _, outsider = await identity(api, "eve")
    key = AESGCM.generate_key(bit_length=256)
    attachment = str(uuid4())
    original = b"synthetic private voice-note contents" * 16
    ciphertext = seal(original, key, attachment, "original")
    blob, reservation = await upload(api, sender, ciphertext)
    message = envelope(bob, bob_device, [blob])
    admitted = await api.post("/v1/messages", headers=sender, json=message)
    assert admitted.status_code == 200 and admitted.json()["state"] == "accepted"

    pending_upload = dict(reservation, id=str(uuid4()))
    assert (
        await api.post("/v1/media/uploads", headers=sender, json=pending_upload)
    ).status_code == 200

    def reopened(**changes):
        new_settings = Settings(**(settings.model_dump() | changes))
        restarted = create_app(
            new_settings, database=db, verifier=TestVerifier(), clock=lambda: NOW
        )
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=restarted), base_url="https://vipi.test"
        )

    path = f"/v1/media/{blob}/ciphertext"
    async with reopened(media_enabled=False) as disabled:
        assert (await disabled.get(path, headers=recipient)).status_code == 404
        pending = (
            await disabled.get("/v1/messages/pending", headers=recipient)
        ).json()["messages"]
        assert [row["id"] for row in pending] == [message["id"]]

    async with reopened(media_draining=True) as drain:
        capability = await drain.get(
            f"/v1/media/capability/{bob['id']}", headers=sender
        )
        assert capability.json() == {"version": 0, "device_id": bob_device}
        assert (
            await drain.post("/v1/media/uploads", headers=sender, json=reservation)
        ).status_code == 200
        assert (
            await drain.post("/v1/media/uploads", headers=sender, json=pending_upload)
        ).json()["state"] == "uploading"
        assert (
            await drain.put(
                f"/v1/media/{pending_upload['id']}/ciphertext",
                headers=sender,
                content=ciphertext,
            )
        ).status_code == 200
        assert (
            await drain.get(f"/v1/media/uploads/{pending_upload['id']}", headers=sender)
        ).json()["state"] == "ready"

        fresh = await drain.post(
            "/v1/media/uploads", headers=sender, json=dict(reservation, id=str(uuid4()))
        )
        assert (fresh.status_code, fresh.json()) == (503, {"error": "media_draining"})
        blocked = await drain.post(
            "/v1/messages", headers=sender, json=envelope(bob, bob_device, [blob])
        )
        assert (blocked.status_code, blocked.json()) == (
            503,
            {"error": "media_draining"},
        )
        assert (
            await drain.post("/v1/messages", headers=sender, json=message)
        ).json() == admitted.json()
        conflict = await drain.post(
            "/v1/messages",
            headers=sender,
            json=dict(message, attachment_ids=[pending_upload["id"]]),
        )
        assert conflict.status_code == 409
        assert (await drain.get(path, headers=outsider)).status_code == 404
        for state in ("accepted", "delivered"):
            assert (
                await drain.get(f"/v1/messages/{message['id']}", headers=sender)
            ).json()["state"] == state
            response = await drain.get(path, headers=recipient)
            assert response.status_code == 200 and response.content == ciphertext
            aad = f"vipi-attachment-v1\0{attachment}\0original".encode()
            assert (
                AESGCM(key).decrypt(ciphertext[:12], response.content[12:], aad)
                == original
            )
            assert (
                await drain.post(
                    f"/v1/messages/{message['id']}/receipt", headers=recipient
                )
            ).json()["state"] == "delivered"
        retry = await drain.post("/v1/messages", headers=sender, json=message)
        assert retry.json()["state"] == "delivered"

        direct = envelope(bob, bob_device, [])
        del direct["attachment_ids"]
        assert (await drain.post("/v1/messages", headers=sender, json=direct)).json()[
            "state"
        ] == "accepted"
        inbox = (await drain.get("/v1/messages/pending", headers=recipient)).json()[
            "messages"
        ]
        assert [row["id"] for row in inbox] == [direct["id"]]
        assert (
            await drain.post(f"/v1/messages/{direct['id']}/receipt", headers=recipient)
        ).json()["state"] == "delivered"
        assert (
            await drain.delete(
                f"/v1/media/uploads/{pending_upload['id']}", headers=sender
            )
        ).json() == {"cancelled": True}

    async with db.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(MediaGrant)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(PendingMessage)) == 2
        )
        assert (await session.get(MediaBlob, blob)).ciphertext_sha256 == sha256(
            ciphertext
        ).hexdigest()
