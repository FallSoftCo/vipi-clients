"""Disabled-by-default Groups API, separate from launch chat admission."""
import base64
import binascii
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .db import User

from . import groups
from .delivery import DeliveryError, Envelope


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateInput(Input):
    id: UUID
    title: str = Field(min_length=1, max_length=80)


class CipherInput(Input):
    id: UUID
    recipient_id: UUID
    recipient_device_id: UUID
    cipher_type: Literal[2, 3]
    ciphertext: str = Field(min_length=44, max_length=87384, repr=False)


class MessageInput(Input):
    id: UUID
    epoch: int = Field(ge=1)
    created_at: AwareDatetime
    envelopes: list[CipherInput] = Field(max_length=16)


class ControlInput(MessageInput):
    invited_user_id: UUID | None = None


class MutationInput(Input):
    request_id: UUID
    expected_epoch: int = Field(ge=1)
    control: MessageInput | None = None


class RenameInput(MutationInput):
    title: str = Field(min_length=1, max_length=80)


class InviteInput(MutationInput):
    user_id: UUID


class RoleInput(MutationInput):
    role: Literal["owner", "admin", "member"]



def install(app, settings, db, now, principal, user_for, phone_for, rate):
    async def enabled():
        if not settings.groups_enabled:
            raise DeliveryError("groups_not_available", 404)

    router = APIRouter(prefix="/v1/groups", dependencies=[Depends(enabled)])

    @router.get("")
    async def listing(request: Request, p=Depends(principal)):
        await rate(p, "groups-list", 60)
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            await session.execute(select(User).where(User.id == user.id).with_for_update()
                .execution_options(populate_existing=True))
            user = await user_for(session, p)
            await phone_for(session, request, user)
            return await groups.list_groups(session, user.id, now=now())

    @router.post("")
    async def create(body: CreateInput, request: Request, p=Depends(principal)):
        await rate(p, "groups-create", 10)
        try:
            async with db.sessions.begin() as session:
                user = await user_for(session, p)
                await phone_for(session, request, user)
                result = await groups.create(session, actor_id=user.id, group_id=str(body.id), title=body.title, now=now())
                await user_for(session, p)
                await phone_for(session, request, user)
                return result
        except IntegrityError:
            raise DeliveryError("group_request_conflict", 409) from None

    @router.get("/{group_id}")
    async def detail(group_id: UUID, request: Request, p=Depends(principal)):
        await rate(p, "groups-detail", 120)
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            await phone_for(session, request, user)
            group, roster, _ = await groups.lock_group(session, str(group_id), user.id)
            groups.member_for(roster, user.id)
            await user_for(session, p)
            await phone_for(session, request, user)
            return await groups.snapshot(session, group, roster)

    async def mutation(group_id, body, request, p, action, **extra):
        await rate(p, "groups-mutate", 60)
        try:
            async with db.sessions.begin() as session:
                user = await user_for(session, p)
                device = await phone_for(session, request, user)
                control = None
                if body.control is not None:
                    try:
                        envelopes = tuple(Envelope(str(e.id), user.id, device.id, str(e.recipient_id),
                            str(e.recipient_device_id), body.control.created_at,
                            base64.b64decode(e.ciphertext, validate=True), e.cipher_type) for e in body.control.envelopes)
                    except (ValueError, binascii.Error):
                        raise DeliveryError("invalid_ciphertext") from None
                    control = groups.Fanout(str(body.control.id), body.control.epoch, body.control.created_at,
                        envelopes, "control")
                result = await groups.mutate(session, group_id=str(group_id), actor_id=user.id,
                    request_id=str(body.request_id), expected_epoch=body.expected_epoch,
                    action=action, now=now(), control=control, device_id=device.id,
                    max_bytes=settings.max_message_bytes, max_pending=settings.max_pending_per_recipient, **extra)
                await user_for(session, p)
                await phone_for(session, request, user)
                return result
        except IntegrityError:
            raise DeliveryError("group_request_conflict", 409) from None

    @router.patch("/{group_id}")
    async def rename(group_id: UUID, body: RenameInput, request: Request, p=Depends(principal)):
        return await mutation(group_id, body, request, p, "rename", title=body.title)

    @router.post("/{group_id}/invitations")
    async def invite(group_id: UUID, body: InviteInput, request: Request, p=Depends(principal)):
        return await mutation(group_id, body, request, p, "invite", target_id=str(body.user_id))

    @router.post("/{group_id}/invitations/{invite_id}/accept")
    async def accept_invite(group_id: UUID, invite_id: UUID, body: MutationInput, request: Request, p=Depends(principal)):
        return await mutation(group_id, body, request, p, "accept", invite_id=str(invite_id))

    @router.post("/{group_id}/invitations/{invite_id}/decline")
    async def decline_invite(group_id: UUID, invite_id: UUID, body: MutationInput, request: Request, p=Depends(principal)):
        return await mutation(group_id, body, request, p, "decline", invite_id=str(invite_id))

    @router.delete("/{group_id}/invitations/{invite_id}")
    async def cancel_invite(group_id: UUID, invite_id: UUID, body: MutationInput, request: Request, p=Depends(principal)):
        return await mutation(group_id, body, request, p, "cancel-invite", invite_id=str(invite_id))

    @router.patch("/{group_id}/members/{user_id}")
    async def role(group_id: UUID, user_id: UUID, body: RoleInput, request: Request, p=Depends(principal)):
        return await mutation(group_id, body, request, p, "role", target_id=str(user_id), role=body.role)

    @router.delete("/{group_id}/members/{user_id}")
    async def remove(group_id: UUID, user_id: UUID, body: MutationInput, request: Request, p=Depends(principal)):
        return await mutation(group_id, body, request, p, "remove", target_id=str(user_id))

    @router.post("/{group_id}/leave")
    async def leave(group_id: UUID, body: MutationInput, request: Request, p=Depends(principal)):
        return await mutation(group_id, body, request, p, "leave")

    async def fanout(group_id, body, request, p, *, kind="message"):
        await rate(p, "groups-send", 120)
        try:
            decoded = [base64.b64decode(e.ciphertext, validate=True) for e in body.envelopes]
        except (ValueError, binascii.Error):
            raise DeliveryError("invalid_ciphertext") from None
        try:
            async with db.sessions.begin() as session:
                user = await user_for(session, p)
                device = await phone_for(session, request, user)
                envelopes = tuple(Envelope(str(e.id), user.id, device.id, str(e.recipient_id),
                    str(e.recipient_device_id), body.created_at, raw, e.cipher_type)
                    for e, raw in zip(body.envelopes, decoded, strict=True))
                result = await groups.send(session, group_id=str(group_id), actor_id=user.id, device_id=device.id,
                    fanout=groups.Fanout(str(body.id), body.epoch, body.created_at, envelopes, kind,
                        str(body.invited_user_id) if isinstance(body, ControlInput) and body.invited_user_id else None), now=now(),
                    max_bytes=settings.max_message_bytes, max_pending=settings.max_pending_per_recipient)
                await user_for(session, p)
                await phone_for(session, request, user)
                return result
        except IntegrityError:
            raise DeliveryError("group_request_conflict", 409) from None

    @router.post("/{group_id}/messages")
    async def send(group_id: UUID, body: MessageInput, request: Request, p=Depends(principal)):
        return await fanout(group_id, body, request, p)

    @router.post("/{group_id}/controls")
    async def control(group_id: UUID, body: ControlInput, request: Request, p=Depends(principal)):
        return await fanout(group_id, body, request, p, kind="control")

    app.include_router(router)
