"""Bounded conversation hints and explicit visible-message read receipts.

Typing has no durable record. Read state reuses the delivery ledger and its
existing retention window; legacy clients continue to see it as delivered.
"""

from sqlalchemy import and_, or_, select

from .db import Block, Device, PendingMessage, User
from .delivery import DeliveryError, utc
from .events import notify, notify_chat


async def conversation_devices(session, user_id, device_id, peer_id, *, lock=False):
    if user_id == peer_id:
        raise DeliveryError("conversation_unavailable", 404)
    query = (
        select(User)
        .where(
            User.id.in_([user_id, peer_id]),
            User.deleted.is_(False),
            User.suspended.is_(False),
        )
        .order_by(User.id)
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    if len((await session.scalars(query)).all()) != 2:
        raise DeliveryError("conversation_unavailable", 404)
    own = await session.get(Device, device_id, populate_existing=True)
    if own is None or own.user_id != user_id or not own.active:
        raise DeliveryError("device_revoked", 401)
    blocked = await session.scalar(
        select(Block).where(
            or_(
                and_(Block.blocker_id == user_id, Block.blocked_id == peer_id),
                and_(Block.blocker_id == peer_id, Block.blocked_id == user_id),
            )
        )
    )
    if blocked is not None:
        raise DeliveryError("conversation_unavailable", 404)
    peers = (
        await session.scalars(
            select(Device).where(Device.user_id == peer_id, Device.active.is_(True))
        )
    ).all()
    if len(peers) != 1:
        raise DeliveryError("conversation_unavailable", 404)
    return own, peers[0]


async def established(session, user_id, device_id, peer_id, peer_device_id, now):
    # A changed device must establish its own encrypted conversation first.
    # Server-side relationship evidence lasts only as long as the existing
    # delivery ledger; an old contact can establish it again by sending.
    return (
        await session.scalar(
            select(PendingMessage.id)
            .where(
                or_(
                    and_(
                        PendingMessage.sender_id == user_id,
                        PendingMessage.sender_device_id == device_id,
                        PendingMessage.recipient_id == peer_id,
                        PendingMessage.recipient_device_id == peer_device_id,
                    ),
                    and_(
                        PendingMessage.sender_id == peer_id,
                        PendingMessage.sender_device_id == peer_device_id,
                        PendingMessage.recipient_id == user_id,
                        PendingMessage.recipient_device_id == device_id,
                    ),
                ),
                or_(
                    PendingMessage.state.in_(("delivered", "read")),
                    and_(
                        PendingMessage.state == "accepted",
                        PendingMessage.expires_at > now,
                    ),
                ),
            )
            .limit(1)
        )
        is not None
    )


async def typing(session, user_id, device_id, peer_id, active, *, now):
    _, peer = await conversation_devices(
        session, user_id, device_id, peer_id, lock=True
    )
    if not await established(session, user_id, device_id, peer_id, peer.id, now):
        raise DeliveryError("conversation_unavailable", 404)
    await notify_chat(
        session, peer.id, {"event": "typing", "peer": user_id, "active": active}
    )


async def receipts(session, user_id, device_id, peer_id, seen, check, *, now):
    seen, check = list(dict.fromkeys(seen)), list(dict.fromkeys(check))
    # Always consume the supplied read-outbox IDs. Unknown, blocked, expired,
    # or foreign IDs must not become a per-message existence oracle.
    try:
        await conversation_devices(session, user_id, device_id, peer_id, lock=True)
    except DeliveryError as error:
        if error.status == 404:
            return {"acknowledged": seen, "read": []}
        raise
    incoming = (
        (
            await session.scalars(
                select(PendingMessage)
                .where(
                    PendingMessage.id.in_(seen),
                    PendingMessage.sender_id == peer_id,
                    PendingMessage.recipient_id == user_id,
                    PendingMessage.recipient_device_id == device_id,
                )
                .order_by(PendingMessage.id)
                .with_for_update()
            )
        ).all()
        if seen
        else []
    )
    changed_devices = set()
    for item in incoming:
        if item.state == "accepted" and utc(item.expires_at) <= utc(now):
            continue
        if item.state not in ("accepted", "delivered", "read"):
            continue
        if item.state == "read":
            continue
        if item.state == "accepted":
            # Explicit seen is stronger than a delivery ACK. It can race the
            # ordinary ACK safely, clearing ciphertext and exposing delivered
            # to a legacy sender without a separate read timestamp/schema.
            await notify(session, item.sender_device_id)
        item.state, item.ciphertext = "read", None
        changed_devices.add(item.sender_device_id)
    await session.flush()
    for sender_device in changed_devices:
        await notify_chat(
            session, sender_device, {"event": "receipts_changed", "peer": user_id}
        )
    read = (
        set(
            (
                await session.scalars(
                    select(PendingMessage.id).where(
                        PendingMessage.id.in_(check),
                        PendingMessage.sender_id == user_id,
                        PendingMessage.sender_device_id == device_id,
                        PendingMessage.recipient_id == peer_id,
                        PendingMessage.state == "read",
                    )
                )
            ).all()
        )
        if check
        else set()
    )
    return {"acknowledged": seen, "read": [item for item in check if item in read]}


async def event_visible(session, user_id, device_id, event, *, now):
    try:
        _, peer = await conversation_devices(session, user_id, device_id, event["peer"])
    except DeliveryError:
        return False
    if event["event"] == "typing":
        return await established(
            session, user_id, device_id, peer.user_id, peer.id, now
        )
    return True
