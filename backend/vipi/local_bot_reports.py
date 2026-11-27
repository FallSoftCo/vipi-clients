"""Explicitly selected local vBot replies; never a generation gateway."""

from datetime import timedelta
import hashlib
import hmac
import json

from sqlalchemy import func, select

from .db import LocalBotReport, User
from .delivery import DeliveryError
from .reports import report_cipher


async def submit(
    session,
    *,
    user_id,
    report_id,
    provider,
    reason,
    selected_reply,
    consent_version,
    secret,
    now,
):
    if consent_version != "local-bot-report-v1":
        raise DeliveryError("report_consent_required", 400)
    try:
        valid_reply = (
            bool(selected_reply.strip()) and len(selected_reply.encode("utf-8")) <= 4000
        )
    except UnicodeError:
        valid_reply = False
    if (
        provider not in ("gemini-nano", "apple-foundation-models")
        or reason not in ("harmful", "inaccurate", "other")
        or not valid_reply
    ):
        raise DeliveryError("invalid_bot_report", 400)
    # Same user lock as deletion; do not create an orphan report after erasure.
    user = (
        await session.execute(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if not user or user.deleted or user.suspended:
        raise DeliveryError("account_unavailable", 409)
    payload = {
        "provider": provider,
        "reason": reason,
        "selected_reply": selected_reply,
        "consent_version": consent_version,
    }
    raw = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode()
    digest = hmac.new(
        secret.encode(), b"vipi-local-bot-report-fingerprint-v1\0" + raw, hashlib.sha256
    ).hexdigest()
    previous = await session.get(LocalBotReport, report_id)
    if previous:
        if previous.user_id != user_id or not hmac.compare_digest(
            previous.fingerprint, digest
        ):
            raise DeliveryError("report_id_conflict", 409)
        return {"reported": True, "report_id": report_id}
    count = (
        await session.execute(
            select(func.count())
            .select_from(LocalBotReport)
            .where(
                LocalBotReport.user_id == user_id,
                LocalBotReport.created_at > now - timedelta(days=1),
            )
        )
    ).scalar_one()
    if count >= 20:
        raise DeliveryError("report_limit_reached", 429)
    session.add(
        LocalBotReport(
            id=report_id,
            user_id=user_id,
            payload=report_cipher(secret, local_bot=True).encrypt(raw),
            fingerprint=digest,
            created_at=now,
            expires_at=now + timedelta(days=30),
        )
    )
    return {"reported": True, "report_id": report_id}
