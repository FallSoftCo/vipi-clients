"""Explicit dual-proof login migration; never merge encrypted accounts by email."""
import hashlib
import hmac
from uuid import UUID

from sqlalchemy import select

from .accounts import active_device
from .db import IdentityLinkReceipt, User, VipiTrialEligibilityLink
from .deletion import deletion_for, lock_account_lifecycle
from .delivery import DeliveryError, utc
from .eligibility import eligibility_hash, transfer_original_trial
from .identity_authorities import FALLSOFT_VIPI, LEGACY_VIPI, raw_shared_subject


def link_hash(value: str, service_secret: str) -> str:
    return hmac.new(service_secret.encode(), b"vipi-identity-link-v1\0" + value.encode(), hashlib.sha256).hexdigest()


async def source_was_linked(session, subject: str, service_secret: str) -> bool:
    if await session.scalar(select(IdentityLinkReceipt.request_id).where(
            IdentityLinkReceipt.source_hash == link_hash(subject, service_secret))) is not None:
        return True
    # App-only deletion discards retry/account/device metadata, but these two
    # eligibility HMACs remain. An old pre-deletion legacy token cannot recreate
    # a parallel Vipi profile under its former identity.
    return await session.scalar(select(VipiTrialEligibilityLink.source_hash).where(
        VipiTrialEligibilityLink.source_hash == eligibility_hash(subject, service_secret))) is not None


async def link_identity(session, *, source, target, request_id: str, account_id: str,
                        device_id: str, device_secret: str, service_secret: str, now):
    if source.authority != LEGACY_VIPI.id or target.authority != FALLSOFT_VIPI.id:
        raise DeliveryError("identity_link_authority_mismatch", 409)
    try:
        target_raw = raw_shared_subject(target.subject)
        if str(UUID(device_id)) != device_id:
            raise ValueError()
    except ValueError:
        raise DeliveryError("identity_link_invalid", 400) from None
    for proof in (source, target):
        if not 0 <= utc(now).timestamp() - proof.authenticated_at <= 600:
            raise DeliveryError("recent_sign_in_required", 401)
    for subject in sorted((source.subject, target.subject)):
        await lock_account_lifecycle(session, subject, service_secret)
    old_hash, new_hash = (link_hash(p.subject, service_secret) for p in (source, target))
    device_hash = link_hash("device:" + device_id, service_secret)
    receipt = await session.get(IdentityLinkReceipt, request_id)
    user = (await session.execute(select(User).where(User.id == account_id).with_for_update())).scalar_one_or_none()
    if not user or user.deleted:
        raise DeliveryError("identity_link_account_unavailable", 409)
    if user.suspended:
        raise DeliveryError("account_restricted", 403)
    if min(source.authenticated_at, target.authenticated_at) < user.minimum_auth_time:
        raise DeliveryError("recent_sign_in_required", 401)
    await active_device(session, account_id, device_id, device_secret, service_secret=service_secret)
    if receipt:
        if receipt.account_id != account_id or not all(hmac.compare_digest(a, b) for a, b in (
                (receipt.source_hash, old_hash), (receipt.target_hash, new_hash), (receipt.device_hash, device_hash))) or user.subject != target.subject:
            raise DeliveryError("identity_link_conflict", 409)
    else:
        if user.subject != source.subject:
            raise DeliveryError("identity_link_conflict", 409)
        occupied = await session.scalar(select(User.id).where(User.subject == target.subject))
        if occupied is not None or await source_was_linked(session, source.subject, service_secret):
            raise DeliveryError("identity_link_conflict", 409)
        for proof in (source, target):
            deletion = await deletion_for(session, proof.subject, service_secret)
            if deletion and deletion.finished_at is None:
                raise DeliveryError("account_deletion_pending", 409)
            if deletion and proof.authenticated_at <= utc(deletion.created_at).timestamp():
                raise DeliveryError("recent_sign_in_required", 401)
        await transfer_original_trial(session, source=source.subject, target=target.subject,
            user=user, service_secret=service_secret)
        user.subject = target.subject
        # Keep the original account UUID, device and every encrypted identity.
        user.minimum_auth_time = max(user.minimum_auth_time, min(source.authenticated_at, target.authenticated_at))
        receipt = IdentityLinkReceipt(request_id=request_id, account_id=account_id,
            source_hash=old_hash, target_hash=new_hash, device_hash=device_hash, created_at=utc(now))
        session.add(receipt)
        await session.flush()
    return {"request_id": request_id, "account_id": account_id, "authority_id": FALLSOFT_VIPI.id,
            "authentication_subject": target_raw, "binding_revision": 1}
