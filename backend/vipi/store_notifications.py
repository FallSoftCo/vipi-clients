"""Authenticated store events invalidate durable grants, never grant access.

Payloads/tokens are not retained. Only event IDs and fingerprints are kept for
deduplication. Current store APIs remain authoritative during reconciliation.
"""

import base64
import binascii
import hashlib
import json
import re
from uuid import UUID

import jwt
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .auth import AuthenticationError, RSAKeyCache
from .db import BillingNotification, Entitlement, User
from .delivery import DeliveryError


class PubSubVerifier(RSAKeyCache):
    def __init__(self, settings, *, transport=None):
        super().__init__(
            "https://www.googleapis.com/oauth2/v3/certs", transport=transport
        )
        self.settings = settings

    async def verify(self, token):
        try:
            if not 32 <= len(token) <= 16384:
                raise ValueError()
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if (
                header.get("alg") != "RS256"
                or not isinstance(kid, str)
                or not 1 <= len(kid) <= 200
            ):
                raise ValueError()
            claims = jwt.decode(
                token,
                await self._key(kid),
                algorithms=["RS256"],
                audience=self.settings.google_rtdn_audience,
                issuer=["accounts.google.com", "https://accounts.google.com"],
                leeway=15,
                options={
                    "require": [
                        "iss",
                        "sub",
                        "aud",
                        "iat",
                        "exp",
                        "email",
                        "email_verified",
                    ]
                },
            )
            if (
                claims["email"] != self.settings.google_rtdn_service_account
                or claims["email_verified"] is not True
                or type(claims["iat"]) is not int
                or type(claims["exp"]) is not int
                or not 0 < claims["exp"] - claims["iat"] <= 3600
            ):
                raise ValueError()
        except (ValueError, KeyError, TypeError, jwt.PyJWTError, AuthenticationError):
            raise DeliveryError("notification_unauthorized", 401) from None


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def retain(db, *, store, event_id, digest, transaction_id, now, environment=None):
    if not isinstance(event_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,128}", event_id
    ):
        raise DeliveryError("notification_invalid", 400)
    async with db.sessions.begin() as session:
        insert = (
            pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
        )
        new = (
            await session.execute(
                insert(BillingNotification)
                .values(store=store, id=event_id, fingerprint=digest, created_at=now)
                .on_conflict_do_nothing()
                .returning(BillingNotification.id)
            )
        ).scalar_one_or_none()
        if new is None:
            old = await session.get(BillingNotification, (store, event_id))
            if old.fingerprint != digest:
                raise DeliveryError("notification_conflict", 409)
            return
        if transaction_id is None:
            return
        query = select(Entitlement).where(
            Entitlement.store == store, Entitlement.transaction_id == transaction_id
        )
        if environment is not None:
            query = query.where(Entitlement.environment == environment)
        rows = (
            (await session.execute(query.order_by(Entitlement.user_id, Entitlement.id)))
            .scalars()
            .all()
        )
        for candidate in rows:
            owner = (
                await session.execute(
                    select(User).where(User.id == candidate.user_id).with_for_update()
                )
            ).scalar_one_or_none()
            if owner is None or owner.deleted:
                continue
            row = (
                await session.execute(
                    select(Entitlement)
                    .where(Entitlement.id == candidate.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
            if row is not None and not row.superseded:
                row.refresh_generation += 1
                row.next_attempt_at = now


def install(app, settings, db, subscriptions, now, *, google_transport=None):
    verifier = PubSubVerifier(settings, transport=google_transport)
    app.state.pubsub_verifier = verifier

    @app.post("/v1/store-notifications/google", status_code=204)
    async def google(request: Request):
        if (
            not all(
                (
                    settings.google_rtdn_audience,
                    settings.google_rtdn_service_account,
                    settings.google_rtdn_subscription,
                )
            )
            or "google" not in subscriptions.providers
        ):
            raise DeliveryError("notifications_unavailable", 503)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise DeliveryError("notification_unauthorized", 401)
        await verifier.verify(auth[7:])
        try:
            envelope = await request.json()
            if envelope["subscription"] != settings.google_rtdn_subscription:
                raise ValueError()
            message = envelope["message"]
            data = json.loads(base64.b64decode(message["data"], validate=True))
            if (
                data["version"] != "1.0"
                or data["packageName"] != settings.google_package_name
            ):
                raise ValueError()
            kinds = [
                name
                for name in (
                    "subscriptionNotification",
                    "voidedPurchaseNotification",
                    "testNotification",
                    "oneTimeProductNotification",
                    "pendingRefundReviewNotification",
                )
                if name in data
            ]
            if len(kinds) != 1:
                raise ValueError()
            transaction = None
            if kinds[0] in ("subscriptionNotification", "voidedPurchaseNotification"):
                token = data[kinds[0]]["purchaseToken"]
                if (
                    not isinstance(token, str)
                    or not 1 <= len(token) <= 4096
                    or any(c.isspace() for c in token)
                ):
                    raise ValueError()
                transaction = hashlib.sha256(token.encode()).hexdigest()
            await retain(
                db,
                store="google",
                event_id=message["messageId"],
                digest=fingerprint(data),
                transaction_id=transaction,
                now=now(),
            )
        except (ValueError, KeyError, TypeError, binascii.Error):
            raise DeliveryError("notification_invalid", 400) from None

    @app.post("/v1/store-notifications/apple", status_code=204)
    async def apple(request: Request):
        provider = subscriptions.providers.get("apple")
        if provider is None:
            raise DeliveryError("notifications_unavailable", 503)
        try:
            body = await request.json()
            signed = body["signedPayload"]
            if not isinstance(signed, str) or not 20 <= len(signed) <= 90000:
                raise ValueError()
            notification = await provider.notification(signed)
            event_id, transaction, digest = notification[:3]
            environment = (
                notification[3] if len(notification) == 4 else provider.environment
            )
            UUID(event_id)
            if environment not in ("Production", "Sandbox"):
                raise ValueError()
            await retain(
                db,
                store="apple",
                event_id=("P_" if environment == "Production" else "S_") + event_id,
                digest=digest,
                transaction_id=transaction,
                now=now(),
                environment=environment,
            )
        except DeliveryError as error:
            if error.code in (
                "purchase_environment_mismatch",
                "notification_app_identifier_mismatch",
            ):
                raise DeliveryError("notification_invalid", 400) from None
            raise
        except (ValueError, KeyError, TypeError):
            raise DeliveryError("notification_invalid", 400) from None
