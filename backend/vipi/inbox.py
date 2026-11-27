"""Recipient inbox pagination and encrypted envelope wire formats."""

import base64
import binascii
import hashlib
import hmac
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select

from .db import Device, PendingMessage
from .delivery import DeliveryError, utc


PAGE_SIZE = 100


def encode_cursor(
    device_id: str, accepted_at: datetime, message_id: str, secret: str
) -> str:
    data = json.dumps(
        [1, device_id, utc(accepted_at).isoformat(), message_id], separators=(",", ":")
    ).encode()
    signature = hmac.digest(secret.encode(), b"vipi-inbox-v1\0" + data, hashlib.sha256)
    return base64.urlsafe_b64encode(data + signature).decode().rstrip("=")


def decode_cursor(value: str, device_id: str, secret: str) -> tuple[datetime, str]:
    try:
        if not value or len(value) > 512:
            raise ValueError()
        raw = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
        data, signature = raw[:-32], raw[-32:]
        if not hmac.compare_digest(
            signature,
            hmac.digest(secret.encode(), b"vipi-inbox-v1\0" + data, hashlib.sha256),
        ):
            raise ValueError()
        version, device, accepted, message_id = json.loads(data)
        if version != 1 or device != device_id:
            raise ValueError()
        instant = datetime.fromisoformat(accepted)
        if instant.tzinfo is None:
            raise ValueError()
        return utc(instant), str(UUID(message_id))
    except (ValueError, TypeError, binascii.Error, UnicodeError):
        raise DeliveryError("invalid_inbox_cursor") from None


def message_status(item: PendingMessage) -> dict:
    return {
        "id": item.id,
        "state": "delivered" if item.state == "read" else item.state,
        "expires_at": utc(item.expires_at).isoformat(),
    }


def encrypted_envelope(item: PendingMessage) -> dict:
    return {
        "id": item.id,
        "sender_id": item.sender_id,
        "sender_device_id": item.sender_device_id,
        "recipient_device_id": item.recipient_device_id,
        "created_at": utc(item.created_at).isoformat(),
        "cipher_type": item.cipher_type,
        "ciphertext": base64.b64encode(item.ciphertext).decode(),
    }


def inbox_message(item: PendingMessage) -> dict:
    result = message_status(item) | encrypted_envelope(item)
    if item.group_id:
        result.update(
            group_id=item.group_id,
            group_epoch=item.group_epoch,
            group_message_id=item.group_message_id,
            group_kind=item.group_kind,
        )
    return result


async def pending_page(
    session,
    device: Device,
    *,
    now: datetime,
    reads_chat_features: bool,
    reads_groups: bool,
    after: str | None,
    secret: str,
) -> dict:
    """Read one keyset page while the caller holds the authenticated user's row lock."""
    query = select(PendingMessage).where(
        PendingMessage.recipient_device_id == device.id,
        PendingMessage.state == "accepted",
        PendingMessage.expires_at > now,
    )
    if not reads_chat_features:
        # A downgraded installation can retain the same device credentials.
        if device.chat_features_v1_until is not None:
            device.chat_features_v1_until = None
        query = query.where(PendingMessage.required_chat_features_version == 0)
    if not reads_groups:
        query = query.where(PendingMessage.is_direct)
    if after:
        accepted_at, message_id = decode_cursor(after, device.id, secret)
        query = query.where(
            or_(
                PendingMessage.accepted_at > accepted_at,
                and_(
                    PendingMessage.accepted_at == accepted_at,
                    PendingMessage.id > message_id,
                ),
            )
        )
    ordered = query.order_by(PendingMessage.accepted_at, PendingMessage.id)
    found = (await session.scalars(ordered.limit(PAGE_SIZE + 1))).all()
    items = found[:PAGE_SIZE]
    cursor = None
    if len(found) > PAGE_SIZE:
        last = items[-1]
        cursor = encode_cursor(device.id, last.accepted_at, last.id, secret)
    return {"next_cursor": cursor, "messages": [inbox_message(item) for item in items]}
