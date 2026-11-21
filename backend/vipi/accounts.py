import hashlib
import hmac
import re
from datetime import UTC, datetime

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .db import Block, Device, PendingMessage, PublicBundle, PublicPreKey, PushOutbox, PushToken, User
from .delivery import DeliveryError


RESERVED_NAMES = {"vipi", "vbot", "bot", "admin", "administrator", "support", "security", "fallsoft", "mambovipi", "system"}


def normalize_username(value: str) -> str:
    value = value.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,23}", value) or value in RESERVED_NAMES:
        raise DeliveryError("username_unavailable", 409)
    return value


def credential_hash(secret: str, service_secret: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", secret):
        raise DeliveryError("invalid_device_credential", 401)
    return hmac.new(service_secret.encode(), secret.encode(), hashlib.sha256).hexdigest()


async def active_device(session: AsyncSession, user_id: str, device_id: str, secret: str, *, service_secret: str) -> Device:
    digest = credential_hash(secret, service_secret)
    device = await session.get(Device, device_id, populate_existing=True)
    if not device or device.user_id != user_id or not device.active or not hmac.compare_digest(device.credential_hash, digest):
        raise DeliveryError("device_revoked", 401)
    return device


async def register_device(session: AsyncSession, *, user_id: str, device_id: str, secret: str,
                          replace_active: bool, service_secret: str, now: datetime) -> Device:
    user = (await session.execute(select(User).where(User.id == user_id, User.deleted.is_(False), User.suspended.is_(False)).with_for_update())).scalar_one_or_none()
    if not user:
        raise DeliveryError("account_unavailable", 404)
    digest = credential_hash(secret, service_secret)
    existing = await session.get(Device, device_id)
    if existing:
        # Idempotent registration must not reactivate a replaced phone.
        if existing.user_id != user_id or not existing.active or not hmac.compare_digest(existing.credential_hash, digest):
            raise DeliveryError("device_registration_conflict", 409)
        return existing
    previous = (await session.execute(select(Device).where(Device.user_id == user_id, Device.active.is_(True)))).scalars().all()
    if previous and not replace_active:
        raise DeliveryError("device_replacement_confirmation_required", 409)
    for device in previous:
        device.active = False
        await session.execute(delete(PushOutbox).where(PushOutbox.device_id == device.id))
        await session.execute(delete(PushToken).where(PushToken.device_id == device.id))
        await session.execute(delete(PublicPreKey).where(PublicPreKey.device_id == device.id))
        await session.execute(delete(PublicBundle).where(PublicBundle.device_id == device.id))
        # Never redirect ciphertext encrypted for an old identity to a new one.
        await session.execute(update(PendingMessage).where(PendingMessage.recipient_device_id == device.id,
            PendingMessage.state == "accepted").values(ciphertext=None, state="identity_changed"))
    device = Device(id=device_id, user_id=user_id, credential_hash=digest, active=True, created_at=now)
    session.add(device)
    await session.flush()
    return device


async def set_block(session: AsyncSession, *, blocker_id: str, blocked_id: str, blocked: bool, now=None):
    if blocker_id == blocked_id:
        raise DeliveryError("invalid_recipient")
    users = (await session.execute(select(User).where(User.id.in_([blocker_id, blocked_id]),
        User.deleted.is_(False)).order_by(User.id).with_for_update())).scalars().all()
    if len(users) != 2:
        raise DeliveryError("recipient_unavailable", 404)
    entry = await session.get(Block, (blocker_id, blocked_id))
    if blocked and entry is None:
        session.add(Block(blocker_id=blocker_id, blocked_id=blocked_id))
    elif not blocked and entry is not None:
        await session.delete(entry)
    if blocked:
        from .groups import revoke_memberships
        await revoke_memberships(session, blocker_id, now=now or datetime.now(UTC), shared_with=blocked_id)
        await session.execute(update(PendingMessage).where(PendingMessage.state == "accepted", or_(
            (PendingMessage.sender_id == blocked_id) & (PendingMessage.recipient_id == blocker_id),
            (PendingMessage.sender_id == blocker_id) & (PendingMessage.recipient_id == blocked_id)
        )).values(ciphertext=None, state="unavailable"))
