import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .db import Block, Device, PendingMessage, User


class DeliveryError(Exception):
    def __init__(self, code: str, status: int = 400):
        self.code, self.status = code, status


def utc(value: datetime) -> datetime:
    # SQLite test timestamps are naive; production PostgreSQL stores timestamptz.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


CHAT_FEATURE_LEASE = timedelta(days=7)
MAX_UNOPENED_CHAT_EVENTS = 64


def chat_features_version(device: Device | None, now: datetime) -> int:
    return int(bool(device and device.active and device.chat_features_v1_until and utc(device.chat_features_v1_until) > utc(now)))


@dataclass(frozen=True)
class Envelope:
    id: str
    sender_id: str
    sender_device_id: str
    recipient_id: str
    recipient_device_id: str
    created_at: datetime
    ciphertext: bytes
    cipher_type: int = 2
    attachment_ids: tuple[str, ...] = ()
    required_chat_features_version: int = 0


def fingerprint(envelope: Envelope) -> str:
    metadata = json.dumps([envelope.id, envelope.sender_id, envelope.sender_device_id,
        envelope.recipient_id, envelope.recipient_device_id, utc(envelope.created_at).isoformat(), envelope.cipher_type], separators=(",", ":")).encode()
    if envelope.required_chat_features_version:
        metadata += b"\0chat-features-v1"
    if envelope.attachment_ids:
        metadata += b"\0media-v1\0" + json.dumps(sorted(envelope.attachment_ids), separators=(",", ":")).encode()
    return hashlib.sha256(metadata + b"\0" + envelope.ciphertext).hexdigest()


async def accept(session: AsyncSession, envelope: Envelope, *, now: datetime, max_bytes: int = 65536, max_pending: int = 10000, media_draining: bool = False,
                 chat_features_enabled: bool = False) -> PendingMessage:
    """Caller owns the transaction. Lock recipient before checking its queue cap."""
    now, sent = utc(now), utc(envelope.created_at)
    if type(envelope.cipher_type) is not int or envelope.cipher_type not in (2, 3):
        raise DeliveryError("invalid_cipher_type")
    if len(envelope.ciphertext) < 32 or len(envelope.ciphertext) > max_bytes:
        raise DeliveryError("invalid_ciphertext_size")
    if sent > now + timedelta(minutes=5):
        raise DeliveryError("clock_ahead")
    if envelope.required_chat_features_version not in (0, 1) or (envelope.attachment_ids and envelope.required_chat_features_version):
        raise DeliveryError("invalid_chat_features")
    digest = fingerprint(envelope)
    # Lock both users in stable order. Device replacement and blocking take the
    # same locks, so no send can race past a committed revocation.
    users = (await session.execute(select(User).where(User.id.in_([envelope.sender_id, envelope.recipient_id]),
        User.deleted.is_(False), User.suspended.is_(False)).order_by(User.id).with_for_update())).scalars().all()
    available = {user.id: user for user in users}
    if envelope.sender_id not in available:
        raise DeliveryError("device_revoked", 401)
    recipient = available.get(envelope.recipient_id)
    if recipient is None:
        raise DeliveryError("recipient_unavailable", 404)
    sender_device = await session.get(Device, envelope.sender_device_id, populate_existing=True)
    if not sender_device or not sender_device.active or sender_device.user_id != envelope.sender_id:
        raise DeliveryError("device_revoked", 401)
    existing = (await session.execute(select(PendingMessage).where(PendingMessage.id == envelope.id).with_for_update())).scalar_one_or_none()
    if existing:
        if existing.sender_id != envelope.sender_id or existing.fingerprint != digest:
            raise DeliveryError("message_id_conflict", 409)
        if utc(existing.expires_at) <= now and existing.state == "accepted":
            existing.state, existing.ciphertext = "expired", None
        return existing
    if envelope.attachment_ids and media_draining:
        raise DeliveryError("media_draining", 503)
    if sent + timedelta(hours=72) <= now:
        raise DeliveryError("message_expired", 410)
    device = await session.get(Device, envelope.recipient_device_id, populate_existing=True)
    if not device or not device.active or device.user_id != envelope.recipient_id:
        raise DeliveryError("recipient_identity_changed", 409)
    if await Block.exists_between(session, envelope.sender_id, envelope.recipient_id):
        raise DeliveryError("recipient_unavailable", 404)
    if envelope.required_chat_features_version:
        if not chat_features_enabled or not chat_features_version(sender_device, now) or not chat_features_version(device, now):
            raise DeliveryError("chat_features_unavailable", 409)
        # A downgraded reader skips these Signal counters. Count expired unacknowledged
        # envelopes too, for the full device capability lease. All pair admissions hold
        # the same user locks. Ordinary messages remain deliverable at the boundary.
        unopened = select(PendingMessage.id).where(
            PendingMessage.recipient_device_id == device.id,
            PendingMessage.sender_device_id == sender_device.id,
            PendingMessage.required_chat_features_version == 1,
            PendingMessage.state.not_in(("delivered", "read")),
            PendingMessage.accepted_at >= now - CHAT_FEATURE_LEASE,
        ).offset(MAX_UNOPENED_CHAT_EVENTS - 1).limit(1)
        if await session.scalar(unopened):
            raise DeliveryError("chat_features_backlog_full", 429)
    if envelope.attachment_ids and device.media_version < 1:
        raise DeliveryError("recipient_media_unsupported", 409)
    # The recipient row serializes admissions, avoiding a count/insert race.
    from sqlalchemy import func
    count = (await session.execute(select(func.count()).select_from(PendingMessage).where(
        PendingMessage.recipient_id == recipient.id, PendingMessage.state == "accepted", PendingMessage.expires_at > now
    ))).scalar_one()
    if count >= max_pending:
        raise DeliveryError("recipient_queue_full", 429)
    item = PendingMessage(id=envelope.id, sender_id=envelope.sender_id, sender_device_id=envelope.sender_device_id,
        recipient_id=envelope.recipient_id, recipient_device_id=envelope.recipient_device_id, created_at=sent,
        accepted_at=now, expires_at=min(sent, now) + timedelta(hours=72), ciphertext=envelope.ciphertext,
        fingerprint=digest, state="accepted", cipher_type=envelope.cipher_type,
        required_chat_features_version=envelope.required_chat_features_version)
    session.add(item)
    await session.flush()
    if envelope.attachment_ids:
        from .media import grant_attachments
        await grant_attachments(session, envelope, now)
    from .events import notify
    await notify(session, envelope.recipient_device_id)
    return item


async def acknowledge(session: AsyncSession, message_id: str, recipient_id: str, device_id: str, *, now: datetime, allow_groups: bool = False) -> str:
    user = (await session.execute(select(User).where(User.id == recipient_id, User.deleted.is_(False)).with_for_update())).scalar_one_or_none()
    device = await session.get(Device, device_id, populate_existing=True)
    if not user or not device or not device.active or device.user_id != recipient_id:
        raise DeliveryError("device_revoked", 401)
    item = (await session.execute(select(PendingMessage).where(PendingMessage.id == message_id).with_for_update())).scalar_one_or_none()
    if not item or item.recipient_id != recipient_id or item.recipient_device_id != device_id or (not allow_groups and not item.is_direct):
        raise DeliveryError("message_not_found", 404)
    if item.state in ("delivered", "read"):
        return "delivered"
    if item.state != "accepted":
        return item.state
    if utc(item.expires_at) <= utc(now):
        item.ciphertext, item.state = None, "expired"
        return "expired"
    item.ciphertext, item.state = None, "delivered"
    from .events import notify
    await notify(session, item.sender_device_id)
    return "delivered"


async def expire(session: AsyncSession, *, now: datetime) -> int:
    result = await session.execute(update(PendingMessage).where(PendingMessage.state == "accepted", PendingMessage.expires_at <= utc(now)).values(ciphertext=None, state="expired"))
    # Retain only delivery metadata briefly for retry status; no retained bodies.
    await session.execute(delete(PendingMessage).where(PendingMessage.expires_at < utc(now) - timedelta(days=7)))
    return result.rowcount
