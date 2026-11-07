"""Provider-verified entitlements. Purchase credentials never enter logs or responses."""
import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import select

from .db import Entitlement, User
from .delivery import DeliveryError, utc


def billing_account_id(user_id):
    return hashlib.sha256(("co.fallsoft.vipi:" + user_id).encode()).hexdigest()


@dataclass(frozen=True)
class VerifiedPurchase:
    store: str
    reference: str
    transaction_id: str
    product: str
    expires_at: datetime
    revoked: bool
    environment: str
    trial_ends_at: datetime | None = None
    linked_transaction_id: str | None = None
    needs_acknowledgement: bool = False
    store_product: str | None = None


class Subscriptions:
    def __init__(self, settings, db, providers, clock):
        self.settings, self.db, self.providers, self.clock = settings, db, providers, clock
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                   info=b"vipi-store-reference-v1").derive(settings.service_secret.encode())
        self.cipher = Fernet(base64.urlsafe_b64encode(key))

    async def apply(self, user_id, purchase, observed_at):
        # Network verification finishes before taking this lock. Older requests
        # cannot overwrite newer observations, nor transfer another user's grant.
        async with self.db.sessions.begin() as session:
            user = (await session.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one_or_none()
            if not user or user.deleted:
                raise DeliveryError("account_unavailable", 409)
            row = (await session.execute(select(Entitlement).where(
                Entitlement.store == purchase.store, Entitlement.transaction_id == purchase.transaction_id))).scalar_one_or_none()
            if row and row.user_id != user_id:
                raise DeliveryError("purchase_account_mismatch", 409)
            if row and row.verified_at and utc(row.verified_at) > utc(observed_at):
                return
            if purchase.linked_transaction_id:
                previous = (await session.execute(select(Entitlement).where(
                    Entitlement.store == purchase.store,
                    Entitlement.transaction_id == purchase.linked_transaction_id))).scalar_one_or_none()
                if previous and previous.user_id != user_id:
                    raise DeliveryError("purchase_account_mismatch", 409)
                if previous:
                    previous.superseded = True
                else:
                    session.add(Entitlement(id=str(uuid4()), user_id=user_id,
                        store=purchase.store, transaction_id=purchase.linked_transaction_id,
                        product=purchase.product, expires_at=utc(observed_at), revoked=True, superseded=True))
            if row is None:
                row = Entitlement(id=str(uuid4()), user_id=user_id, store=purchase.store,
                                  transaction_id=purchase.transaction_id, superseded=False)
                session.add(row)
            row.product = purchase.product
            row.expires_at = utc(purchase.expires_at)
            row.revoked = purchase.revoked
            row.provider_reference = self.cipher.encrypt(purchase.reference.encode())
            row.verified_at = utc(observed_at)
            row.trial_ends_at = purchase.trial_ends_at
            row.environment = purchase.environment

    async def sync(self, user_id, store, value):
        provider = self.providers.get(store)
        if not provider:
            raise DeliveryError("purchase_verification_unavailable", 503)
        observed_at = self.clock()
        purchase = await provider.verify(value, user_id, initial=True)
        await self.apply(user_id, purchase, observed_at)
        await provider.acknowledge(purchase)
        return await self.snapshot(user_id)

    async def refresh(self, user_id):
        cutoff = self.clock() - timedelta(seconds=self.settings.purchase_freshness_seconds)
        async with self.db.sessions() as session:
            rows = (await session.execute(select(Entitlement).where(
                Entitlement.user_id == user_id, Entitlement.superseded.is_(False)))).scalars().all()
        for row in rows:
            if row.verified_at and utc(row.verified_at) > cutoff:
                continue
            provider = self.providers.get(row.store)
            if not provider or not row.provider_reference:
                continue
            observed_at = self.clock()
            try:
                reference = self.cipher.decrypt(row.provider_reference).decode()
                purchase = await provider.verify(reference, user_id, initial=False)
                await self.apply(user_id, purchase, observed_at)
                await provider.acknowledge(purchase)
            except DeliveryError:
                # Stale grants are inactive in snapshot. Do not invent an expiry
                # or silently mark an unreachable provider as a refund.
                continue

    async def snapshot(self, user_id, *, refresh=True):
        if refresh:
            await self.refresh(user_id)
        now = self.clock()
        cutoff = now - timedelta(seconds=self.settings.purchase_freshness_seconds)
        async with self.db.sessions() as session:
            rows = (await session.execute(select(Entitlement).where(Entitlement.user_id == user_id))).scalars().all()
        if any(not r.revoked and not r.superseded and r.verified_at and utc(r.verified_at) <= cutoff
               and utc(r.expires_at) > now for r in rows):
            # Do not turn a store outage into an invitation to buy a second time.
            raise DeliveryError("purchase_verification_unavailable", 503)
        result = {}
        for name in ("base", "bot_mini"):
            matches = [r for r in rows if r.product == name and not r.revoked and not r.superseded
                       and r.verified_at and utc(r.verified_at) > cutoff and utc(r.expires_at) > now]
            latest = max(matches, key=lambda r: utc(r.expires_at), default=None)
            result[name] = {"active": latest is not None,
                "expires_at": utc(latest.expires_at).isoformat() if latest else None,
                "trial_ends_at": utc(latest.trial_ends_at).isoformat() if latest and latest.trial_ends_at and utc(latest.trial_ends_at) > now else None}
        result["bot_mini"]["available"] = result["base"]["active"] and result["bot_mini"]["active"]
        result["billing_account_id"] = billing_account_id(user_id)
        result["app_account_token"] = user_id
        result["purchases_ready"] = {"apple": "apple" in self.providers, "google": "google" in self.providers}
        return result

    async def require(self, user_id, *, bot=False):
        state = await self.snapshot(user_id)
        if not state["base"]["active"]:
            raise DeliveryError("base_subscription_required", 402)
        if bot and not state["bot_mini"]["available"]:
            raise DeliveryError("bot_subscription_required", 402)
        return state
