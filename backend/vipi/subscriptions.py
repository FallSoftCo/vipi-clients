"""Provider-verified entitlements. Purchase credentials never enter logs or responses."""
import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import and_, or_, select

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

    async def apply(self, user_id, purchase, observed_at, *, generation=None, lease_token=None):
        # Network verification finishes before taking this lock. Older requests
        # cannot overwrite newer observations, nor transfer another user's grant.
        async with self.db.sessions.begin() as session:
            user = (await session.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one_or_none()
            if not user or user.deleted:
                raise DeliveryError("account_unavailable", 409)
            row = (await session.execute(select(Entitlement).where(
                Entitlement.store == purchase.store, Entitlement.transaction_id == purchase.transaction_id))).scalar_one_or_none()
            if lease_token and (row is None or row.lease_token != lease_token):
                return
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
                                  transaction_id=purchase.transaction_id, superseded=False,
                                  refresh_generation=0, completed_generation=0)
                session.add(row)
            row.product = purchase.product
            row.expires_at = utc(purchase.expires_at)
            row.revoked = purchase.revoked
            row.provider_reference = self.cipher.encrypt(purchase.reference.encode())
            row.verified_at = utc(observed_at)
            row.trial_ends_at = purchase.trial_ends_at
            row.environment = purchase.environment
            if generation is not None:
                row.completed_generation = max(row.completed_generation, generation)
            row.attempts = 0
            row.next_attempt_at = (self.clock() if row.refresh_generation > row.completed_generation
                else self.clock() + timedelta(seconds=self.settings.purchase_freshness_seconds))

    async def sync(self, user_id, store, value):
        provider = self.providers.get(store)
        if not provider:
            raise DeliveryError("purchase_verification_unavailable", 503)
        observed_at = self.clock()
        purchase = await provider.verify(value, user_id, initial=True)
        await self.apply(user_id, purchase, observed_at)
        await provider.acknowledge(purchase)
        return await self.snapshot(user_id)

    async def reconcile_one(self):
        now = self.clock()
        cutoff = now - timedelta(seconds=self.settings.purchase_freshness_seconds)
        async with self.db.sessions.begin() as session:
            row = (await session.execute(select(Entitlement).where(
                Entitlement.store.in_(self.providers), Entitlement.superseded.is_(False),
                Entitlement.provider_reference.is_not(None),
                or_(Entitlement.lease_until.is_(None), Entitlement.lease_until <= now),
                or_(Entitlement.next_attempt_at <= now, and_(Entitlement.next_attempt_at.is_(None),
                    or_(Entitlement.verified_at.is_(None), Entitlement.verified_at <= cutoff))),
                or_(Entitlement.expires_at > now - timedelta(days=7),
                    Entitlement.refresh_generation > Entitlement.completed_generation))
                .order_by(Entitlement.next_attempt_at.asc().nullsfirst(), Entitlement.id)
                .limit(1).with_for_update(skip_locked=True))).scalar_one_or_none()
            if row is None:
                return False
            token, generation = str(uuid4()), row.refresh_generation
            row.lease_token, row.lease_until = token, now + timedelta(minutes=2)
            row.attempts += 1
            row_id, user_id, store = row.id, row.user_id, row.store
            reference = self.cipher.decrypt(row.provider_reference).decode()
        successful, expired_reference = False, False
        try:
            provider = self.providers[store]
            purchase = await provider.verify(reference, user_id, initial=False)
            await self.apply(user_id, purchase, now, generation=generation, lease_token=token)
            await provider.acknowledge(purchase)
            successful = True
        except DeliveryError as error:
            successful = False
            expired_reference = error.code == "purchase_invalid"
        finally:
            # An expired lease cannot overwrite a newer worker's outcome.
            async with self.db.sessions.begin() as session:
                row = (await session.execute(select(Entitlement).where(
                    Entitlement.id == row_id, Entitlement.lease_token == token).with_for_update())).scalar_one_or_none()
                if row:
                    row.lease_token = None; row.lease_until = None
                    if expired_reference and utc(row.expires_at) <= self.clock():
                        # Google invalidates sufficiently old expired tokens.
                        # Do not keep an obsolete event permanently runnable.
                        row.completed_generation = max(row.completed_generation, generation)
                        row.next_attempt_at = self.clock() + timedelta(days=1)
                    elif not successful:
                        row.next_attempt_at = self.clock() + timedelta(seconds=min(3600, 30 * 2 ** min(row.attempts, 7)))
        return True

    async def snapshot(self, user_id):
        # Only the durable worker and explicit purchase/restore perform remote
        # reads. Chat cannot repeat a store call or reset provider backoff.
        now = self.clock()
        cutoff = now - timedelta(seconds=self.settings.purchase_outage_seconds)
        reviewer = user_id in self.settings.reviewer_user_ids
        async with self.db.sessions() as session:
            if reviewer:
                user = await session.get(User, user_id)
                if user is None or user.deleted or user.suspended:
                    raise DeliveryError("account_unavailable", 403)
            rows = (await session.execute(select(Entitlement).where(Entitlement.user_id == user_id))).scalars().all()
        if not reviewer and any(not r.revoked and not r.superseded and r.verified_at and utc(r.verified_at) <= cutoff
               and utc(r.expires_at) > now for r in rows):
            # Do not turn a store outage into an invitation to buy a second time.
            raise DeliveryError("purchase_verification_unavailable", 503)
        result = {}
        for name in ("base", "bot_mini"):
            matches = [r for r in rows if r.product == name and not r.revoked and not r.superseded
                       and r.verified_at and utc(r.verified_at) > cutoff and utc(r.expires_at) > now]
            latest = max(matches, key=lambda r: utc(r.expires_at), default=None)
            if reviewer:
                result[name] = {"active": True, "expires_at": None, "trial_ends_at": None,
                    "access_source": "review_complimentary", "review_access": True}
                continue
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
