"""Private, signed adapter for the separately confirmed Fallsoft deletion flow.

No WorkOS calls. Erasure and re-provision holds commit together. The only
permanent state is keyed hashes preventing old sessions restoring deleted data.
"""
import hashlib
import hmac
import json
import re
import secrets
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import Request
from sqlalchemy import delete, select

from .db import AccountDeletion, GlobalDeletionHold, GlobalDeletionReceipt, User, VipiTrialEligibilityLink
from .deletion import lock_account_lifecycle, lock_lifecycle_hash, request_deletion, subject_hash
from .delivery import DeliveryError, utc
from .eligibility import eligibility_hash, erase_for_global_fallsoft_deletion
from .identity_authorities import canonical_shared_subject

CONTRACT = "vipi-fallsoft-deletion-1"
PATH = "/internal/fallsoft-deletion"


async def provision_blocked(session, subject, service_secret):
    return await session.get(GlobalDeletionHold, eligibility_hash(subject, service_secret)) is not None


def verify_operation(raw, headers, path, key, now):
    """Authenticate exact bytes before parsing; exact retries are idempotent."""
    timestamp = headers.get("x-fallsoft-deletion-time", "")
    nonce = headers.get("x-fallsoft-deletion-nonce", "")
    signature = headers.get("x-fallsoft-deletion-signature", "")
    if (len(raw) > 4096 or path not in (PATH + "/status", PATH + "/erase") or
            not re.fullmatch(r"[0-9]{10}", timestamp) or
            abs(int(timestamp) - int(utc(now).timestamp())) > 60 or
            not re.fullmatch(r"[A-Za-z0-9_-]{32}", nonce) or not re.fullmatch(r"[a-f0-9]{64}", signature)):
        raise DeliveryError("deletion_request_not_verified", 401)
    signed = "\n".join(("fallsoft-account-deletion-v1", "vipi", "POST", path, timestamp, nonce,
                         hashlib.sha256(raw).hexdigest()))
    expected = hmac.new(key.encode(), signed.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise DeliveryError("deletion_request_not_verified", 401)
    def unique(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise ValueError("duplicate key")
            result[name] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=unique)
        if set(value) != {"requestId", "subject", "scope", "subjectHash", "consentVersion", "contractVersion"}:
            raise ValueError()
        request_id = UUID(value["requestId"])
        if request_id.version != 4 or str(request_id) != value["requestId"]:
            raise ValueError()
        if (value["scope"] != "fallsoft" or value["consentVersion"] != "fallsoft-account-deletion-1" or
                value["contractVersion"] != CONTRACT or not re.fullmatch(r"[a-f0-9]{64}", value["subjectHash"])):
            raise ValueError()
        canonical_shared_subject(value["subject"])
        return value
    except (ValueError, TypeError, KeyError, AttributeError):
        raise DeliveryError("invalid_deletion_request", 400) from None


def result(operation, receipt=None):
    value = {"requestId": operation["requestId"], "scope": "fallsoft", "application": "vipi",
             "subjectHash": operation["subjectHash"], "status": "complete" if receipt else "not_started"}
    if receipt:
        value.update(reprovisionBlocked=True, receiptId=receipt.receipt_id)
    return value


async def inspect(session, operation, service_secret):
    receipt = await session.get(GlobalDeletionReceipt, operation["requestId"])
    if receipt:
        digest = eligibility_hash(canonical_shared_subject(operation["subject"]), service_secret)
        if (not hmac.compare_digest(receipt.subject_hash, digest) or
                not hmac.compare_digest(receipt.central_subject_hash, operation["subjectHash"])):
            raise DeliveryError("deletion_request_conflict", 409)
        if await session.get(GlobalDeletionHold, digest) is None:
            raise DeliveryError("deletion_status_unavailable", 503)
    return result(operation, receipt)


async def erase(session, operation, service_secret, now):
    subject = canonical_shared_subject(operation["subject"])
    # Bind a request UUID even when two different identities race for it.
    await lock_account_lifecycle(session, "global-request:" + operation["requestId"], service_secret)
    await lock_account_lifecycle(session, subject, service_secret)
    existing = await inspect(session, operation, service_secret)
    if existing["status"] == "complete":
        return existing
    digest = eligibility_hash(subject, service_secret)
    aliases = (await session.scalars(select(VipiTrialEligibilityLink.source_hash).where(
        VipiTrialEligibilityLink.target_hash == digest))).all()
    for key in sorted(set(aliases)):
        await lock_lifecycle_hash(session, key)
    for key in {digest, *aliases}:
        if await session.get(GlobalDeletionHold, key) is None:
            session.add(GlobalDeletionHold(subject_hash=key, created_at=utc(now)))
    user = (await session.execute(select(User).where(User.subject == subject).with_for_update())).scalar_one_or_none()
    if user:
        await request_deletion(session, subject=subject, account_id=user.id,
            receipt_secret=secrets.token_urlsafe(32), service_secret=service_secret, now=now)
    await erase_for_global_fallsoft_deletion(session, subject=subject, service_secret=service_secret)
    # The central receipt replaces app-only status receipts, including older joins.
    await session.execute(delete(AccountDeletion).where(AccountDeletion.subject_hash == subject_hash(subject, service_secret)))
    receipt = GlobalDeletionReceipt(request_id=operation["requestId"], subject_hash=digest,
        central_subject_hash=operation["subjectHash"], receipt_id=uuid4().hex, finished_at=utc(now))
    session.add(receipt)
    await session.flush()
    return result(operation, receipt)


async def expire_receipts(session, now):
    # Holds contain no raw identity/account/device and survive receipt expiry.
    await session.execute(delete(GlobalDeletionReceipt).where(GlobalDeletionReceipt.finished_at < utc(now) - timedelta(days=7)))


def install(app, settings, db, clock):
    if not settings.global_deletion_enabled:
        return

    async def handle(request, mutation):
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 4096:
                raise DeliveryError("invalid_deletion_request", 413)
        operation = verify_operation(bytes(raw), request.headers, request.url.path,
            settings.global_deletion_secret.get_secret_value(), clock())
        async with db.sessions.begin() as session:
            if mutation:
                return await erase(session, operation, settings.service_secret, clock())
            return await inspect(session, operation, settings.service_secret)

    @app.post(PATH + "/status")
    async def status(request: Request):
        return await handle(request, False)

    @app.post(PATH + "/erase")
    async def erase_account(request: Request):
        return await handle(request, True)
