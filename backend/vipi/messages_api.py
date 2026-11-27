"""HTTP endpoints for sending, receiving and acknowledging messages."""

import base64
import binascii
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query, Request
from sqlalchemy import select
from starlette.responses import JSONResponse, Response

from .api_inputs import NotificationEnvelopeInput, ReceiptsInput, SendInput, TypingInput
from .auth import Principal
from .db import PendingMessage, User
from .delivery import DeliveryError, Envelope, accept, acknowledge, utc
from .inbox import message_status, pending_page
from .rates import consume


def install(app, settings, db, now, principal, user_for, phone_for, rate):
    def reads_groups(request, user):
        return (
            request.headers.get("X-Vipi-Group-Protocol") == "1"
            and settings.group_protocol_for(user.id) == 1
        )

    @app.post("/v1/messages")
    async def send(
        body: SendInput, request: Request, p: Annotated[Principal, Depends(principal)]
    ):
        if body.attachment_ids and not settings.media_enabled:
            raise DeliveryError("media_unavailable", 404)
        if len(set(body.attachment_ids)) != len(body.attachment_ids):
            raise DeliveryError("invalid_media_references")
        await rate(p, "send", 120)
        # Every authenticated, unrestricted account can send. No trial clock,
        # receipt, purchase provider or billing outage participates in delivery.
        try:
            ciphertext = base64.b64decode(body.ciphertext, validate=True)
        except (ValueError, binascii.Error):
            raise DeliveryError("invalid_ciphertext")
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            device = await phone_for(session, request, user)
            value = await accept(
                session,
                Envelope(
                    str(body.id),
                    user.id,
                    device.id,
                    str(body.recipient_id),
                    str(body.recipient_device_id),
                    body.created_at,
                    ciphertext,
                    body.cipher_type,
                    tuple(str(ident) for ident in body.attachment_ids),
                    body.required_chat_features_version,
                ),
                now=now(),
                max_bytes=settings.max_message_bytes,
                max_pending=settings.max_pending_per_recipient,
                enqueue_push=True,
                media_draining=settings.media_draining,
                chat_features_enabled=settings.chat_features_enabled,
            )
            return message_status(value)

    @app.post("/v1/notifications/envelope")
    async def notification_envelope(body: NotificationEnvelopeInput, request: Request):
        from .push import preview_envelope

        async with db.sessions.begin() as session:
            item = await preview_envelope(
                session,
                ticket=body.ticket,
                device_id=request.headers.get("X-Vipi-Device-ID", ""),
                device_secret=request.headers.get("X-Vipi-Device-Secret", ""),
                secret=settings.service_secret,
                now=now(),
            )
            await consume(
                session,
                subject=request.headers["X-Vipi-Device-ID"],
                scope="notification-envelope",
                now=now().timestamp(),
                limit=120,
            )
            return JSONResponse(item, headers={"Cache-Control": "no-store"})

    @app.get("/v1/messages/pending")
    async def pending(
        request: Request,
        response: Response,
        p: Annotated[Principal, Depends(principal)],
        after: Annotated[str | None, Query(max_length=512)] = None,
    ):
        response.headers["Cache-Control"] = "private, no-store"
        await rate(p, "inbox", 120)
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            await session.execute(
                select(User).where(User.id == user.id).with_for_update()
            )
            device = await phone_for(session, request, user)
            return await pending_page(
                session,
                device,
                now=now(),
                after=after,
                secret=settings.service_secret,
                reads_chat_features=request.headers.get("X-Vipi-Chat-Features") == "1",
                reads_groups=reads_groups(request, user),
            )

    @app.get("/v1/messages/{message_id}")
    async def status(
        message_id: UUID, request: Request, p: Annotated[Principal, Depends(principal)]
    ):
        await rate(p, "status", 120)
        async with db.sessions() as session:
            user = await user_for(session, p)
            device = await phone_for(session, request, user)
            item = await session.get(PendingMessage, str(message_id))
            if (
                not item
                or item.sender_id != user.id
                or item.sender_device_id != device.id
                or (not item.is_direct and not reads_groups(request, user))
            ):
                raise DeliveryError("message_not_found", 404)
            result = message_status(item)
            if item.state == "accepted" and utc(item.expires_at) <= now():
                result["state"] = "expired"
            return result

    @app.post("/v1/messages/{message_id}/receipt")
    async def receipt(
        message_id: UUID, request: Request, p: Annotated[Principal, Depends(principal)]
    ):
        await rate(p, "receipt", 240)
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            device = await phone_for(session, request, user)
            state = await acknowledge(
                session,
                str(message_id),
                user.id,
                device.id,
                now=now(),
                allow_groups=reads_groups(request, user),
            )
            return {"id": str(message_id), "state": state}

    @app.post("/v1/conversations/{peer_id}/typing")
    async def typing_event(
        peer_id: UUID,
        body: TypingInput,
        request: Request,
        p: Annotated[Principal, Depends(principal)],
    ):
        await rate(p, "chat-typing", 60)
        from .chat_events import typing

        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            device = await phone_for(session, request, user)
            await typing(
                session, user.id, device.id, str(peer_id), body.active, now=now()
            )
        return {"accepted": True}

    @app.post("/v1/conversations/{peer_id}/receipts")
    async def conversation_receipts(
        peer_id: UUID,
        body: ReceiptsInput,
        request: Request,
        p: Annotated[Principal, Depends(principal)],
    ):
        await rate(p, "chat-receipts", 240)
        from .chat_events import receipts

        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            device = await phone_for(session, request, user)
            return await receipts(
                session,
                user.id,
                device.id,
                str(peer_id),
                [str(item) for item in body.seen],
                [str(item) for item in body.check],
                now=now(),
            )
