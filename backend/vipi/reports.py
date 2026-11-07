"""Explicitly selected reports. No ambient access to private chat plaintext."""
import base64
from datetime import timedelta
import hashlib
import hmac
import json
from uuid import uuid4

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import delete, func, or_, select, update

from .db import Device, ModerationAction, PendingMessage, PushOutbox, User, UserReport
from .delivery import DeliveryError


def report_cipher(secret, *, bot=False):
    domain = b"vipi-bot-report-v1" if bot else b"vipi-user-report-v1"
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=domain).derive(secret.encode())
    return Fernet(base64.urlsafe_b64encode(key))


async def submit(session, *, user_id, report_id, reported_user_id, message_id,
                 reason, selected_text, consent_version, secret, now):
    if consent_version != "report-v1":
        raise DeliveryError("report_consent_required", 400)
    if user_id == reported_user_id or reason not in ("spam", "harassment", "harmful", "other"):
        raise DeliveryError("invalid_report", 400)
    if (message_id is None) != (selected_text is None):
        raise DeliveryError("invalid_report", 400)
    if selected_text is not None:
        try:
            valid = bool(selected_text.strip()) and len(selected_text.encode("utf-8")) <= 32768
        except UnicodeError:
            valid = False
        if not valid:
            raise DeliveryError("invalid_report", 400)
    # Reports are allowed after blocking. Stable user locks serialize with deletion.
    users = (await session.execute(select(User).where(User.id.in_([user_id, reported_user_id]),
        User.deleted.is_(False)).order_by(User.id).with_for_update()
        .execution_options(populate_existing=True))).scalars().all()
    if len(users) != 2 or any(u.suspended for u in users if u.id == user_id):
        raise DeliveryError("report_unavailable", 404)
    payload = {"reported_user_id": reported_user_id, "message_id": message_id,
               "reason": reason, "selected_text": selected_text, "consent_version": consent_version}
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    digest = hmac.new(secret.encode(), b"vipi-user-report-fingerprint-v1\0" + raw, hashlib.sha256).hexdigest()
    previous = await session.get(UserReport, report_id)
    if previous:
        if previous.user_id != user_id or not hmac.compare_digest(previous.fingerprint, digest):
            raise DeliveryError("report_id_conflict", 409)
        return {"reported": True, "report_id": report_id}
    recent = (await session.execute(select(func.count()).select_from(UserReport).where(
        UserReport.user_id == user_id, UserReport.created_at > now - timedelta(days=1)))).scalar_one()
    if recent >= 20:
        raise DeliveryError("report_limit_reached", 429)
    # Transport metadata can corroborate participants only, never plaintext or
    # authorship. Older locally retained messages may outlive relay metadata.
    envelope = await session.get(PendingMessage, message_id) if message_id else None
    if envelope and (envelope.sender_id != reported_user_id or envelope.recipient_id != user_id):
        raise DeliveryError("invalid_report", 400)
    payload["participants_corroborated"] = envelope is not None
    encrypted = report_cipher(secret).encrypt(json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode())
    session.add(UserReport(id=report_id, user_id=user_id, reported_user_id=reported_user_id,
        payload=encrypted, fingerprint=digest, created_at=now, expires_at=now + timedelta(days=30)))
    return {"reported": True, "report_id": report_id}


async def restrict(session, *, user_id, suspended, operator, reason, now):
    """Administrative action only; report counts never automatically restrict users."""
    user = (await session.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one_or_none()
    if not user or user.deleted:
        raise DeliveryError("account_unavailable", 404)
    if not operator or len(operator) > 128 or reason not in ("spam", "harassment", "harmful", "appeal", "other"):
        raise ValueError("Invalid operator or reason")
    if user.suspended == suspended:
        return False
    user.suspended = suspended
    if suspended:
        await session.execute(update(PendingMessage).where(
            or_(PendingMessage.sender_id == user_id, PendingMessage.recipient_id == user_id),
            PendingMessage.state == "accepted").values(state="cancelled", ciphertext=None))
        devices = select(Device.id).where(Device.user_id == user_id)
        await session.execute(delete(PushOutbox).where(PushOutbox.device_id.in_(devices)))
    session.add(ModerationAction(id=str(uuid4()), user_id=user_id, operator=operator,
        action="suspend" if suspended else "restore", reason=reason, created_at=now))
    return True
