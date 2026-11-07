"""Erase Vipi records atomically and reliably finish identity-provider cleanup."""
import hashlib
import hmac
import re
from datetime import timedelta
from uuid import uuid4

import httpx
from sqlalchemy import delete, or_, select, text

from .db import AccountDeletion, Block, BotReport, Device, Entitlement, KeyClaim, PendingMessage, PublicBundle, PublicPreKey, PushOutbox, PushToken, RateWindow, Reservation, UsageBucket, User
from .delivery import DeliveryError, utc


def subject_hash(subject: str, service_secret: str) -> str:
    return hmac.new(service_secret.encode(), b"vipi-account-deletion-v1\0" + subject.encode(), hashlib.sha256).hexdigest()


def receipt_hash(secret: str, service_secret: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", secret):
        raise DeliveryError("deletion_receipt_unavailable", 404)
    return hmac.new(service_secret.encode(), b"vipi-deletion-receipt-v1\0" + secret.encode(), hashlib.sha256).hexdigest()


async def deletion_for(session, subject: str, service_secret: str):
    return (await session.execute(select(AccountDeletion).where(
        AccountDeletion.subject_hash == subject_hash(subject, service_secret)))).scalar_one_or_none()


async def lock_account_lifecycle(session, subject: str, service_secret: str):
    # Registration and deletion must also serialize BEFORE a profile exists.
    # This short transaction-scoped PostgreSQL lock is independent of devices.
    if session.get_bind().dialect.name == "postgresql":
        digest = hmac.new(service_secret.encode(), b"vipi-account-lifecycle-v1\0" + subject.encode(), hashlib.sha256).digest()
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int.from_bytes(digest[:8], "big", signed=True)})


async def request_deletion(session, *, subject: str, account_id: str, receipt_secret: str, service_secret: str, now):
    digest = receipt_hash(receipt_secret, service_secret)
    await lock_account_lifecycle(session, subject, service_secret)
    # The same user lock used by registration, delivery, claims and blocking
    # serializes deletion with those operations. Recheck after waiting for it.
    user = (await session.execute(select(User).where(User.subject == subject).with_for_update())).scalar_one_or_none()
    previous = await deletion_for(session, subject, service_secret)
    if previous:
        if previous.account_id != account_id:
            raise DeliveryError("account_changed", 409)
        if not hmac.compare_digest(previous.receipt_hash, digest):
            raise DeliveryError("deletion_receipt_unavailable", 404)
        return previous
    if user and user.id != account_id:
        raise DeliveryError("account_changed", 409)
    if not user and (await session.get(User, account_id) or await session.get(AccountDeletion, account_id)):
        raise DeliveryError("account_changed", 409)
    devices = select(Device.id).where(Device.user_id == account_id)
    await session.execute(delete(PushOutbox).where(PushOutbox.device_id.in_(devices)))
    await session.execute(delete(PushToken).where(PushToken.device_id.in_(devices)))
    await session.execute(delete(KeyClaim).where(or_(KeyClaim.requester_device_id.in_(devices),
        KeyClaim.recipient_id == account_id, KeyClaim.recipient_device_id.in_(devices))))
    await session.execute(delete(PublicPreKey).where(PublicPreKey.device_id.in_(devices)))
    await session.execute(delete(PublicBundle).where(PublicBundle.device_id.in_(devices)))
    await session.execute(delete(PendingMessage).where(or_(PendingMessage.sender_id == account_id, PendingMessage.recipient_id == account_id)))
    await session.execute(delete(Block).where(or_(Block.blocker_id == account_id, Block.blocked_id == account_id)))
    for model in (BotReport, Entitlement, Reservation, UsageBucket, Device):
        await session.execute(delete(model).where(model.user_id == account_id))
    await session.execute(delete(RateWindow).where(RateWindow.subject == subject))
    if user:
        await session.delete(user)
    job = AccountDeletion(account_id=account_id, subject=subject, subject_hash=subject_hash(subject, service_secret), receipt_hash=digest,
                          created_at=utc(now), next_attempt_at=utc(now), attempts=0)
    session.add(job)
    await session.flush()
    return job


async def deletion_status(session, *, account_id: str, receipt_secret: str, service_secret: str):
    digest = receipt_hash(receipt_secret, service_secret)
    job = await session.get(AccountDeletion, account_id)
    if not job or not hmac.compare_digest(job.receipt_hash, digest):
        raise DeliveryError("deletion_receipt_unavailable", 404)
    return {"account_id": job.account_id, "status": "deleted" if job.finished_at else "deletion_requested"}


class WorkOSUserDeleter:
    def __init__(self, settings, *, transport=None):
        if not settings.account_deletion_enabled or not settings.workos_dedicated_user_pool or not settings.workos_api_key:
            raise ValueError("Identity cleanup is not configured")
        self.http = httpx.AsyncClient(timeout=10, follow_redirects=False, transport=transport,
            headers={"Authorization": "Bearer " + settings.workos_api_key.get_secret_value()})

    async def close(self):
        await self.http.aclose()

    async def delete(self, subject):
        if not re.fullmatch(r"user_[A-Za-z0-9_]{1,123}", subject):
            raise ValueError("Invalid identity subject")
        # A missing user is successful on retry after an uncertain response.
        response = await self.http.delete("https://api.workos.com/user_management/users/" + subject)
        if response.status_code not in (200, 204, 404):
            raise RuntimeError("identity_cleanup_unavailable")


async def process_deletions(db, deleter, *, now, limit=10):
    """Short DB leases; no transaction is held open across the provider request."""
    now = utc(now)
    counts = {"finished": 0, "retry": 0, "lease_lost": 0}
    for _ in range(limit):
        lease = str(uuid4())
        async with db.sessions.begin() as session:
            job = (await session.execute(select(AccountDeletion).where(
                AccountDeletion.finished_at.is_(None), AccountDeletion.next_attempt_at <= now,
                or_(AccountDeletion.lease_until.is_(None), AccountDeletion.lease_until <= now))
                .order_by(AccountDeletion.next_attempt_at, AccountDeletion.account_id)
                .limit(1).with_for_update(skip_locked=True))).scalar_one_or_none()
            if not job:
                break
            job.lease_token = lease; job.lease_until = now + timedelta(minutes=2); job.attempts += 1
            account_id, subject = job.account_id, job.subject
        try:
            await deleter.delete(subject)
            success = True
        except Exception:
            # Do not retain provider bodies, identity values or API credentials.
            success = False
        async with db.sessions.begin() as session:
            job = (await session.execute(select(AccountDeletion).where(AccountDeletion.account_id == account_id)
                                         .with_for_update())).scalar_one_or_none()
            if not job or job.lease_token != lease:
                counts["lease_lost"] += 1
                continue
            job.lease_token = None; job.lease_until = None
            if success:
                job.subject = None; job.finished_at = now; job.error_code = None
                counts["finished"] += 1
            else:
                job.next_attempt_at = now + timedelta(seconds=min(3600, 15 * 2**min(job.attempts, 8)))
                job.error_code = "identity_cleanup_unavailable"
                counts["retry"] += 1
    return counts


async def expire_deletion_receipts(session, now):
    # Seven days exceeds the accepted access-token lifetime; failed jobs stay
    # durable and continue retrying instead of silently abandoning deletion.
    await session.execute(delete(AccountDeletion).where(AccountDeletion.finished_at < utc(now) - timedelta(days=7)))
