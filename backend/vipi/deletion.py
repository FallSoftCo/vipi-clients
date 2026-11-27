"""Erase Vipi records only. Shared Fallsoft identity deletion is a separate service."""

import hashlib
import hmac
import re
from datetime import timedelta

from sqlalchemy import delete, or_, select, text

from .db import (
    AccountDeletion,
    Block,
    BotReport,
    LocalBotReport,
    Device,
    Entitlement,
    IdentityLinkReceipt,
    KeyClaim,
    ModerationAction,
    PendingMessage,
    PublicBundle,
    PublicPreKey,
    PushOutbox,
    PushToken,
    RateWindow,
    Reservation,
    SurveyDecision,
    UsageBucket,
    User,
    UserReport,
)
from .delivery import DeliveryError, utc
from .eligibility import eligibility_hash, original_trial


def subject_hash(subject: str, service_secret: str) -> str:
    return hmac.new(
        service_secret.encode(),
        b"vipi-account-deletion-v1\0" + subject.encode(),
        hashlib.sha256,
    ).hexdigest()


def receipt_hash(secret: str, service_secret: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", secret):
        raise DeliveryError("deletion_receipt_unavailable", 404)
    return hmac.new(
        service_secret.encode(),
        b"vipi-deletion-receipt-v1\0" + secret.encode(),
        hashlib.sha256,
    ).hexdigest()


async def deletion_for(session, subject: str, service_secret: str):
    return (
        await session.execute(
            select(AccountDeletion)
            .where(
                AccountDeletion.subject_hash == subject_hash(subject, service_secret)
            )
            .order_by(
                AccountDeletion.created_at.desc(), AccountDeletion.account_id.desc()
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def lock_account_lifecycle(session, subject: str, service_secret: str):
    # Registration and deletion must also serialize BEFORE a profile exists.
    # This short transaction-scoped PostgreSQL lock is independent of devices.
    await lock_lifecycle_hash(session, eligibility_hash(subject, service_secret))


async def lock_lifecycle_hash(session, digest: str):
    # One lock family lets global erasure serialize historical linked identities
    # using retained HMACs alone. Never retain the old raw identity just to lock it.
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("invalid_lifecycle_hash")
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": int.from_bytes(bytes.fromhex(digest)[:8], "big", signed=True)},
        )


async def request_deletion(
    session,
    *,
    subject: str,
    account_id: str,
    receipt_secret: str,
    service_secret: str,
    now,
    authenticated_at: int | None = None,
):
    digest = receipt_hash(receipt_secret, service_secret)
    await lock_account_lifecycle(session, subject, service_secret)
    # Resolve retries by the ORIGINAL account, before inspecting a newly joined
    # profile under the same shared identity. An old DELETE cannot erase it.
    previous = await session.get(AccountDeletion, account_id)
    if previous:
        if not hmac.compare_digest(
            previous.subject_hash, subject_hash(subject, service_secret)
        ):
            raise DeliveryError("account_changed", 409)
        if not hmac.compare_digest(previous.receipt_hash, digest):
            raise DeliveryError("deletion_receipt_unavailable", 404)
        return previous
    user = (
        await session.execute(
            select(User).where(User.subject == subject).with_for_update()
        )
    ).scalar_one_or_none()
    latest = await deletion_for(session, subject, service_secret)
    if latest and latest.finished_at is None:
        raise DeliveryError("account_deletion_pending", 409)
    if user and user.id != account_id:
        raise DeliveryError("account_changed", 409)
    if not user and await session.get(User, account_id):
        raise DeliveryError("account_changed", 409)
    if authenticated_at is not None and (
        (user and authenticated_at < user.minimum_auth_time)
        or (latest and authenticated_at <= utc(latest.created_at).timestamp())
    ):
        raise DeliveryError("recent_sign_in_required", 401)
    if user:
        from .billing_identity import retain_account

        if await session.scalar(
            select(Entitlement.id).where(Entitlement.user_id == user.id).limit(1)
        ):
            await retain_account(
                session, subject=subject, user_id=user.id, service_secret=service_secret
            )
        if utc(user.cardless_trial_ends_at) > utc(user.cardless_trial_started_at):
            await original_trial(
                session,
                subject=subject,
                service_secret=service_secret,
                started_at=user.cardless_trial_started_at,
                ends_at=user.cardless_trial_ends_at,
            )
    from .groups import revoke_memberships

    await revoke_memberships(session, account_id, now=now, deleting=True)
    devices = select(Device.id).where(Device.user_id == account_id)
    from .media import erase_account_media

    await erase_account_media(session, account_id, now)
    await session.execute(delete(PushOutbox).where(PushOutbox.device_id.in_(devices)))
    await session.execute(delete(PushToken).where(PushToken.device_id.in_(devices)))
    await session.execute(
        delete(KeyClaim).where(
            or_(
                KeyClaim.requester_device_id.in_(devices),
                KeyClaim.recipient_id == account_id,
                KeyClaim.recipient_device_id.in_(devices),
            )
        )
    )
    await session.execute(
        delete(PublicPreKey).where(PublicPreKey.device_id.in_(devices))
    )
    await session.execute(
        delete(PublicBundle).where(PublicBundle.device_id.in_(devices))
    )
    await session.execute(
        delete(PendingMessage).where(
            or_(
                PendingMessage.sender_id == account_id,
                PendingMessage.recipient_id == account_id,
            )
        )
    )
    await session.execute(
        delete(Block).where(
            or_(Block.blocker_id == account_id, Block.blocked_id == account_id)
        )
    )
    await session.execute(
        delete(UserReport).where(
            or_(
                UserReport.user_id == account_id,
                UserReport.reported_user_id == account_id,
            )
        )
    )
    for model in (
        ModerationAction,
        BotReport,
        LocalBotReport,
        Entitlement,
        Reservation,
        UsageBucket,
        SurveyDecision,
        Device,
    ):
        await session.execute(delete(model).where(model.user_id == account_id))
    await session.execute(delete(RateWindow).where(RateWindow.subject == subject))
    await session.execute(
        delete(IdentityLinkReceipt).where(IdentityLinkReceipt.account_id == account_id)
    )
    if user:
        await session.delete(user)
    job = AccountDeletion(
        account_id=account_id,
        subject=None,
        subject_hash=subject_hash(subject, service_secret),
        receipt_hash=digest,
        created_at=utc(now),
        finished_at=utc(now),
        next_attempt_at=utc(now),
        attempts=0,
    )
    session.add(job)
    await session.flush()
    return job


async def deletion_status(
    session, *, account_id: str, receipt_secret: str, service_secret: str
):
    digest = receipt_hash(receipt_secret, service_secret)
    job = await session.get(AccountDeletion, account_id)
    if not job or not hmac.compare_digest(job.receipt_hash, digest):
        raise DeliveryError("deletion_receipt_unavailable", 404)
    return {
        "account_id": job.account_id,
        "status": "deleted" if job.finished_at else "deletion_requested",
    }


async def expire_deletion_receipts(session, now):
    from .global_deletion import expire_receipts

    await expire_receipts(session, now)
    # Status capabilities expire after seven days. Legacy unfinished identity
    # jobs remain quarantined for explicit reconciliation; no worker dispatches
    # them against the current (possibly shared/different) provider environment.
    await session.execute(
        delete(AccountDeletion).where(
            AccountDeletion.finished_at < utc(now) - timedelta(days=7)
        )
    )
