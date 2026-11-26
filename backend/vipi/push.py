"""Coalesced opaque inbox wakeups. Providers never receive human chat contents."""
import asyncio
import base64
import hashlib
import hmac
import json
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import and_, case, delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .db import Block, Database, Device, PendingMessage, PushOutbox, PushToken, User
from .delivery import DeliveryError, utc
from .inbox import encrypted_envelope


def purpose_cipher(secret, purpose):
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
               info=purpose).derive(secret.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def token_cipher(secret):
    return purpose_cipher(secret, b"vipi-push-token-v1")


def preview_ticket(secret, registration, message_id, now):
    """An encrypted reference to one envelope, never sufficient to retrieve it alone."""
    claims = ["notification-envelope-v1", registration.device_id, registration.fingerprint, message_id]
    return purpose_cipher(secret, b"vipi-notification-envelope-v1").encrypt_at_time(json.dumps(claims).encode(), int(now.timestamp())).decode()


async def preview_envelope(session, *, ticket, device_id, device_secret, secret, now):
    from .accounts import active_device
    from .global_deletion import provision_blocked
    try:
        payload = purpose_cipher(secret, b"vipi-notification-envelope-v1").decrypt_at_time(ticket.encode(), ttl=3600, current_time=int(now.timestamp()))
        purpose, target, fingerprint, message_id = json.loads(payload)
        if purpose != "notification-envelope-v1" or target != device_id:
            raise ValueError()
    except (InvalidToken, ValueError, TypeError, UnicodeError):
        raise DeliveryError("notification_unavailable", 404)
    registration = await session.get(PushToken, device_id)
    message = await session.get(PendingMessage, message_id)
    if (not registration or registration.provider != "apns" or registration.fingerprint != fingerprint or
            not message or message.required_chat_features_version or not message.is_direct or message.recipient_device_id != device_id or message.state not in ("accepted", "delivered") or
            utc(message.expires_at) <= now):
        raise DeliveryError("notification_unavailable", 404)
    await active_device(session, message.recipient_id, device_id, device_secret, service_secret=secret)
    user = await session.get(User, message.recipient_id)
    if (not user or user.deleted or user.suspended or
            user.minimum_auth_time > int(utc(registration.updated_at).timestamp()) or
            await provision_blocked(session, user.subject, secret)):
        raise DeliveryError("notification_unavailable", 404)
    sender = await session.get(User, message.sender_id)
    if not sender or sender.deleted or sender.suspended or await session.get(Block, (user.id, sender.id)) or await session.get(Block, (sender.id, user.id)):
        raise DeliveryError("notification_unavailable", 404)
    # Only earlier envelopes of this exact Signal session can be prerequisites.
    # Leave a longer unprocessed chain to the ordinary paginated inbox.
    ordered = select(PendingMessage).where(PendingMessage.recipient_device_id == device_id,
        PendingMessage.sender_device_id == message.sender_device_id, PendingMessage.sender_id == sender.id,
        PendingMessage.state == "accepted", PendingMessage.expires_at > now,
        or_(PendingMessage.accepted_at < message.accepted_at,
            and_(PendingMessage.accepted_at == message.accepted_at, PendingMessage.id <= message.id)))
    rows = (await session.execute(ordered.order_by(PendingMessage.accepted_at, PendingMessage.id).limit(9))).scalars().all()
    # The extension can open only direct messages. If a group control or
    # group text or silent event precedes this message on the same Signal session, the full
    # client must handle the chain with its authenticated roster and vault.
    if len(rows) > 8 or any(not item.is_direct or item.required_chat_features_version for item in rows):
        raise DeliveryError("notification_unavailable", 404)
    return {"id": message.id, "peer": sender.id, "display_name": sender.display_name,
            "accepted_at": utc(message.accepted_at).timestamp(), "messages": [encrypted_envelope(item) for item in rows]}


async def register(session, *, user_id, device_id, provider, environment, token, secret, now):
    await session.execute(select(User).where(User.id == user_id).with_for_update())
    device = await session.get(Device, device_id, populate_existing=True)
    if not device or not device.active or device.user_id != user_id:
        raise DeliveryError("device_revoked", 401)
    await session.execute(select(PushOutbox).where(PushOutbox.device_id == device_id).with_for_update())
    if provider not in ("fcm", "apns") or environment not in ("sandbox", "production"):
        raise DeliveryError("invalid_push_registration")
    if provider == "apns":
        if not re.fullmatch(r"[a-fA-F0-9]{64,512}", token) or len(token) % 2:
            raise DeliveryError("invalid_push_registration")
        token = token.lower()
    elif environment != "production" or not re.fullmatch(r"[A-Za-z0-9_:\-]{20,4096}", token):
        raise DeliveryError("invalid_push_registration")
    fingerprint = hmac.new(secret.encode(), b"push-token\0" + token.encode(), hashlib.sha256).hexdigest()
    # A phone changing signed-in accounts must not keep the previous account's
    # notifications. The token is secret and supplied by its native OS SDK.
    await session.execute(delete(PushToken).where(PushToken.provider == provider,
        PushToken.environment == environment, PushToken.fingerprint == fingerprint, PushToken.device_id != device_id))
    row = await session.get(PushToken, device_id)
    if row is None:
        row = PushToken(device_id=device_id)
        session.add(row)
    row.provider, row.environment, row.fingerprint = provider, environment, fingerprint
    row.token, row.updated_at = token_cipher(secret).encrypt(token.encode()), now
    # A newly enabled token should also wake an already pending inbox.
    latest = (await session.execute(select(PendingMessage).where(PendingMessage.recipient_device_id == device_id,
        PendingMessage.required_chat_features_version == 0, PendingMessage.state == "accepted", PendingMessage.expires_at > now).order_by(PendingMessage.expires_at.desc()).limit(1))).scalar_one_or_none()
    if latest:
        await enqueue(session, device_id, now, latest.expires_at)


async def enqueue(session, device_id, now, expires_at, *, group_event=False):
    insert = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    statement = insert(PushOutbox).values(device_id=device_id, generation=1, next_attempt_at=now,
        expires_at=expires_at, attempts=0, group_event=group_event)
    await session.execute(statement.on_conflict_do_update(index_elements=[PushOutbox.device_id], set_={
        "generation": PushOutbox.generation + 1, "next_attempt_at": now,
        "group_event": or_(PushOutbox.group_event, group_event),
        "expires_at": case((PushOutbox.expires_at > expires_at, PushOutbox.expires_at), else_=expires_at), "attempts": 0}))


class PushProviders:
    def __init__(self, settings, *, transport=None, credentials=None):
        self.settings = settings
        self.http = httpx.AsyncClient(timeout=15, http2=True, follow_redirects=False, transport=transport)
        self.credentials = credentials
        self.auth_lock = asyncio.Lock()
        if not credentials and settings.fcm_service_account_path:
            from google.oauth2 import service_account
            self.credentials = service_account.Credentials.from_service_account_file(settings.fcm_service_account_path,
                scopes=["https://www.googleapis.com/auth/firebase.messaging"])
        self.apns_keys = {
            "production": (settings.apns_key_id, Path(settings.apns_private_key_path).read_bytes() if settings.apns_private_key_path else None),
            "sandbox": (settings.apns_sandbox_key_id, Path(settings.apns_sandbox_private_key_path).read_bytes() if settings.apns_sandbox_private_key_path else None),
        }
        self.apns_tokens = {}

    async def send(self, registration, token, now, expires_at, *, preview=None):
        """sent, invalid, or retry; only a definitive invalid-token reply retires it."""
        ttl = max(0, min(3600, int((utc(expires_at) - now).total_seconds())))
        if ttl == 0:
            return "sent"
        try:
            if registration.provider == "fcm":
                if not self.credentials or not self.settings.fcm_project_id:
                    return "retry"
                async with self.auth_lock:
                    if not self.credentials.valid:
                        from google.auth.transport.requests import Request
                        request = Request()
                        def bounded_request(*args, **kwargs):
                            kwargs["timeout"] = 15
                            return request(*args, **kwargs)
                        await asyncio.to_thread(self.credentials.refresh, bounded_request)
                    access = self.credentials.token
                response = await self.http.post("https://fcm.googleapis.com/v1/projects/" + self.settings.fcm_project_id + "/messages:send",
                    headers={"Authorization": "Bearer " + access}, json={"message": {"token": token,
                        "data": {"kind": "inbox_changed"},
                        "android": {"priority": "high", "ttl": str(ttl) + "s", "collapse_key": "vipi-inbox",
                                    "restricted_package_name": self.settings.google_package_name}}})
                if response.status_code == 200:
                    return "sent"
                errors = response.json().get("error", {}).get("details", [])
                return "invalid" if any(e.get("errorCode") == "UNREGISTERED" for e in errors) else "retry"
            environment = registration.environment
            if environment not in self.apns_keys:
                return "retry"
            key_id, key = self.apns_keys[environment]
            if not all((key, key_id, self.settings.apns_team_id)):
                return "retry"
            timestamp = int(now.timestamp())
            cached = self.apns_tokens.get(environment)
            if cached is None or timestamp - cached[1] >= 1200 or timestamp < cached[1]:
                signed = jwt.encode({"iss": self.settings.apns_team_id, "iat": timestamp}, key,
                    algorithm="ES256", headers={"kid": key_id})
                cached = (signed, timestamp)
                self.apns_tokens[environment] = cached
            host = "api.sandbox.push.apple.com" if environment == "sandbox" else "api.push.apple.com"
            response = await self.http.post("https://" + host + "/3/device/" + token,
                headers={"authorization": "bearer " + cached[0], "apns-topic": self.settings.apns_bundle_id,
                    "apns-push-type": "alert", "apns-priority": "10", "apns-expiration": str(timestamp + ttl),
                    "apns-collapse-id": "vipi-inbox"},
                json={"aps": {"alert": {"title": "Vipi", "loc-key": "You have a new message."}, "sound": "default", "content-available": 1, "mutable-content": 1}, "kind": "inbox_changed",
                      **({"preview": preview} if preview else {})})
            if response.status_code == 200:
                return "sent"
            reason = response.json().get("reason")
            return "invalid" if response.status_code == 410 and reason == "Unregistered" else "retry"
        except Exception:
            # Do not log push tokens, JWTs, vendor bodies or credential URLs.
            return "retry"

    async def close(self):
        await self.http.aclose()


async def process_pushes(db, providers, *, secret, now, limit=100, clock=None, dispatch_seconds=45):
    current = clock or (lambda: now)
    deadline = time.monotonic() + dispatch_seconds
    now = current()
    cipher = token_cipher(secret)
    counts = {"sent": 0, "invalid": 0, "retry": 0, "discarded": 0, "lease_lost": 0}
    async with db.sessions.begin() as session:
        await session.execute(delete(PushOutbox).where(PushOutbox.expires_at <= now))
    for _ in range(limit):
        if time.monotonic() >= deadline:
            break
        now = current()
        lease = str(uuid4())
        async with db.sessions.begin() as session:
            job = (await session.execute(select(PushOutbox).where(PushOutbox.next_attempt_at <= now,
                or_(PushOutbox.lease_until.is_(None), PushOutbox.lease_until <= now))
                .order_by(PushOutbox.next_attempt_at, PushOutbox.device_id).limit(1).with_for_update(skip_locked=True))).scalar_one_or_none()
            if not job:
                break
            device = await session.get(Device, job.device_id)
            registration = await session.get(PushToken, job.device_id)
            pending = (await session.execute(select(PendingMessage).where(PendingMessage.recipient_device_id == job.device_id,
                PendingMessage.required_chat_features_version == 0, PendingMessage.state == "accepted", PendingMessage.expires_at > now).order_by(PendingMessage.accepted_at.desc(), PendingMessage.id.desc()).limit(1))).scalar_one_or_none()
            if utc(job.expires_at) <= now or not device or not device.active or not registration or not (pending or job.group_event):
                await session.delete(job); counts["discarded"] += 1
                continue
            job.lease_token, job.lease_until = lease, now + timedelta(minutes=2)
            job.attempts += 1
            device_id, generation, expires_at = job.device_id, job.generation, job.expires_at
            preview_id = pending.id if pending and pending.is_direct and not job.group_event else None
        try:
            token = cipher.decrypt(registration.token).decode()
            options = {"preview": preview_ticket(secret, registration, preview_id, now)} if registration.provider == "apns" and preview_id else {}
            outcome = await providers.send(registration, token, now, expires_at, **options)
        except Exception:
            outcome = "retry"
        settled_at = current()
        async with db.sessions.begin() as session:
            job = (await session.execute(select(PushOutbox).where(PushOutbox.device_id == device_id).with_for_update())).scalar_one_or_none()
            if not job or job.lease_token != lease:
                counts["lease_lost"] += 1
                continue
            if outcome == "invalid":
                await session.execute(delete(PushToken).where(PushToken.device_id == device_id, PushToken.fingerprint == registration.fingerprint))
            if outcome in ("sent", "invalid") and job.generation == generation:
                await session.delete(job)
            else:
                job.lease_token = job.lease_until = None
                job.next_attempt_at = settled_at if job.generation != generation else settled_at + timedelta(seconds=min(3600, 15 * 2**min(job.attempts, 8)))
            counts[outcome] += 1
    return counts


async def main():
    from .config import Settings
    settings = Settings()
    if settings.recovery_hold:
        # Do not construct database/provider clients or dispatch/expire records.
        return
    db = Database(settings.database_url)
    try:
        await db.check_admission()
    except BaseException:
        await db.close()
        raise
    providers = PushProviders(settings)
    try:
        while True:
            await asyncio.gather(*(process_pushes(db, providers, secret=settings.service_secret,
                now=datetime.now(UTC), clock=lambda: datetime.now(UTC), limit=25) for _ in range(4)))
            await asyncio.sleep(1)
    finally:
        await providers.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
