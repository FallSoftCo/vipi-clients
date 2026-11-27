"""Group membership and one-to-one attachment access on the same relay."""

from base64 import b64encode
from uuid import uuid4

import httpx

from conftest import NOW
from test_api import TestVerifier
from test_groups_api import create, invite_join, settings
from test_media import envelope, identity, upload
from vipi.api import create_app


async def test_group_membership_does_not_grant_access_to_a_direct_attachment(
    db, tmp_path
):
    config = settings(
        groups_enabled=True, media_enabled=True, media_storage_path=str(tmp_path)
    )
    app = create_app(config, database=db, verifier=TestVerifier(), clock=lambda: NOW)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://vipi.test"
    ) as api:
        _, _, sender = await identity(api, "alice")
        bob, bob_device, recipient = await identity(api, "bob")
        eve, eve_device, other_member = await identity(api, "eve")
        group = await create(api, sender)
        group = await invite_join(api, group, sender, bob, recipient)
        group = await invite_join(api, group, sender, eve, other_member)
        group_envelopes = [
            {
                "id": str(uuid4()),
                "recipient_id": user["id"],
                "recipient_device_id": device,
                "cipher_type": 3,
                "ciphertext": b64encode(bytes([i]) * 64).decode(),
            }
            for i, (user, device) in enumerate(
                ((bob, bob_device), (eve, eve_device)), start=1
            )
        ]
        group_message = {
            "id": str(uuid4()),
            "epoch": group["epoch"],
            "created_at": NOW.isoformat(),
            "envelopes": group_envelopes,
        }
        result = await api.post(
            f"/v1/groups/{group['id']}/messages", headers=sender, json=group_message
        )
        assert result.status_code == 200, result.text

        # Exceeds the normal JSON body limit. Only the attachment upload route streams this body.
        opaque_bytes = bytes(range(256)) * 640
        blob, _ = await upload(api, sender, opaque_bytes)
        private_message = envelope(bob, bob_device, [blob])
        posted = await api.post("/v1/messages", headers=sender, json=private_message)
        assert posted.status_code == 200, posted.text

        photo_url = f"/v1/media/{blob}/ciphertext"
        downloaded = await api.get(photo_url, headers=recipient)
        assert downloaded.status_code == 200 and downloaded.content == opaque_bytes
        assert (await api.get(photo_url, headers=other_member)).status_code == 404
        other_inbox = (
            await api.get(
                "/v1/messages/pending",
                headers=other_member | {"X-Vipi-Group-Protocol": "1"},
            )
        ).json()["messages"]
        assert [row["group_message_id"] for row in other_inbox] == [group_message["id"]]
