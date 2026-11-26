"""Public Signal prekeys only. Private key generation and signature verification
belong to the official native libsignal clients, never this directory service.

User row locks serialize registration, publication, claims and blocking. A
publication revision is durable before upload on the client; replaying it cannot
restore consumed one-time keys. Each key ID increases for the life of a device.
"""
import base64
import hashlib
import json
from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select

from .db import Block, Device, KeyClaim, PublicBundle, PublicPreKey, User
from .delivery import DeliveryError, utc


def decode(value, size):
    try:
        data = base64.b64decode(value, validate=True)
        if len(data) != size or base64.b64encode(data).decode() != value:
            raise ValueError()
        return data
    except (ValueError, TypeError):
        raise ValueError("invalid_public_key") from None


class PublicKeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: int = Field(ge=1, le=2_147_483_647)
    key: str = Field(max_length=2092)
    signature: str = Field(max_length=88)

    @field_validator("signature")
    @classmethod
    def signature_bytes(cls, value):
        decode(value, 64)
        return value


class OneTimeInput(PublicKeyInput):
    ec_key: str = Field(max_length=44)

    @field_validator("key")
    @classmethod
    def kem_bytes(cls, value):
        decode(value, 1569)  # libsignal Kyber1024 public serialization, incl. tag.
        return value

    @field_validator("ec_key")
    @classmethod
    def ec_bytes(cls, value):
        decode(value, 33)
        return value


class SignedInput(PublicKeyInput):
    @field_validator("key")
    @classmethod
    def ec_bytes(cls, value):
        decode(value, 33)
        return value


class PublishInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int = Field(ge=1, le=2_147_483_647)
    registration_id: int = Field(ge=1, le=16380)
    identity_key: str = Field(max_length=44)
    signed: SignedInput
    one_time: list[OneTimeInput] = Field(min_length=1, max_length=20)

    @field_validator("identity_key")
    @classmethod
    def identity_bytes(cls, value):
        decode(value, 33)
        return value

    @field_validator("one_time")
    @classmethod
    def distinct_sorted_ids(cls, values):
        ids = [item.id for item in values]
        if ids != sorted(set(ids)):
            raise ValueError("key_ids_must_increase")
        return values


async def lock_users(session, *ids):
    users = (await session.execute(select(User).where(User.id.in_(ids), User.deleted.is_(False), User.suspended.is_(False))
        .order_by(User.id).with_for_update())).scalars().all()
    if len(users) != len(set(ids)):
        raise DeliveryError("recipient_unavailable", 404)


async def require_device(session, user_id, device_id):
    # Authentication may have loaded the device before waiting for our user lock.
    device = (await session.execute(select(Device).where(Device.id == device_id)
        .execution_options(populate_existing=True))).scalar_one_or_none()
    if not device or device.user_id != user_id or not device.active:
        raise DeliveryError("device_revoked", 401)
    return device


async def inventory(session, device_id):
    bundle = await session.get(PublicBundle, device_id)
    count = (await session.execute(select(func.count()).select_from(PublicPreKey)
        .where(PublicPreKey.device_id == device_id))).scalar_one()
    return {"revision": bundle.revision if bundle else 0, "remaining": count}


async def publish(session, *, user_id, device_id, body: PublishInput):
    await lock_users(session, user_id)
    await require_device(session, user_id, device_id)
    digest = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    old = await session.get(PublicBundle, device_id)
    if old and body.revision == old.revision and digest == old.fingerprint:
        return await inventory(session, device_id)
    if body.revision != (old.revision + 1 if old else 1):
        raise DeliveryError("key_revision_conflict", 409)
    identity = decode(body.identity_key, 33)
    if old and (old.identity_key != identity or old.registration_id != body.registration_id):
        raise DeliveryError("identity_replacement_required", 409)
    if old and body.one_time[0].id <= old.high_key_id:
        raise DeliveryError("key_id_reuse", 409)
    signed, signature = decode(body.signed.key, 33), decode(body.signed.signature, 64)
    if old and (body.signed.id < old.signed_key_id or (body.signed.id == old.signed_key_id and
        (signed != old.signed_key or signature != old.signed_signature))):
        raise DeliveryError("signed_key_conflict", 409)
    if (await inventory(session, device_id))["remaining"] + len(body.one_time) > 200:
        raise DeliveryError("key_pool_full", 409)
    bundle = old or PublicBundle(device_id=device_id)
    bundle.registration_id, bundle.identity_key = body.registration_id, identity
    bundle.signed_key_id, bundle.signed_key, bundle.signed_signature = body.signed.id, signed, signature
    bundle.revision, bundle.fingerprint = body.revision, digest
    bundle.high_key_id = body.one_time[-1].id
    session.add(bundle)
    for item in body.one_time:
        session.add(PublicPreKey(device_id=device_id, key_id=item.id, ec_key=decode(item.ec_key, 33),
            kem_key=decode(item.key, 1569), kem_signature=decode(item.signature, 64)))
    await session.flush()
    return await inventory(session, device_id)


async def claim(session, *, user_id, device_id, recipient_id, request_id, now):
    if user_id == recipient_id:
        raise DeliveryError("invalid_recipient")
    await lock_users(session, user_id, recipient_id)
    await require_device(session, user_id, device_id)
    if await Block.exists_between(session, user_id, recipient_id):
        raise DeliveryError("recipient_unavailable", 404)
    target = (await session.execute(select(Device).where(Device.user_id == recipient_id, Device.active.is_(True)))).scalar_one_or_none()
    if not target:
        raise DeliveryError("recipient_unavailable", 404)
    previous = await session.get(KeyClaim, (device_id, request_id))
    if previous:
        if previous.recipient_id != recipient_id:
            raise DeliveryError("key_claim_conflict", 409)
        if previous.recipient_device_id != target.id:
            raise DeliveryError("recipient_identity_changed", 409)
        if utc(previous.created_at) + timedelta(minutes=10) <= utc(now):
            raise DeliveryError("key_claim_expired", 410)
        return json.loads(previous.response)
    bundle = await session.get(PublicBundle, target.id)
    key = (await session.execute(select(PublicPreKey).where(PublicPreKey.device_id == target.id)
        .order_by(PublicPreKey.key_id).limit(1).with_for_update())).scalar_one_or_none()
    if not bundle or not key:
        # Do not downgrade PQXDH to a classical-only handshake or reuse a key.
        raise DeliveryError("recipient_keys_unavailable", 409)
    b64 = lambda data: base64.b64encode(data).decode()
    response = {"request_id": request_id, "user_id": recipient_id, "device_id": target.id,
        "signal_device_id": 1, "registration_id": bundle.registration_id,
        "identity_key": b64(bundle.identity_key), "signed": {"id": bundle.signed_key_id,
            "key": b64(bundle.signed_key), "signature": b64(bundle.signed_signature)},
        "one_time": {"id": key.key_id, "ec_key": b64(key.ec_key), "key": b64(key.kem_key), "signature": b64(key.kem_signature)}}
    await session.delete(key)
    session.add(KeyClaim(requester_device_id=device_id, id=request_id, recipient_id=recipient_id,
        recipient_device_id=target.id, created_at=now, response=json.dumps(response, separators=(",", ":")).encode()))
    await session.flush()
    return response


async def expire_claims(session, now):
    # Public material plus routing metadata; no private keys or message contents.
    await session.execute(delete(KeyClaim).where(KeyClaim.created_at <= utc(now) - timedelta(hours=72)))
