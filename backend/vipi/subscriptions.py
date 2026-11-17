"""Provider-verified entitlements. Purchase credentials never enter logs or responses."""
import base64
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import and_, or_, select

from .db import Entitlement, User
from .delivery import DeliveryError, utc
from .billing_identity import billing_account_id, matches_account
from .deletion import lock_account_lifecycle


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

    async def ownership(self, user_id, expected_subject=None):
        from .global_deletion import provision_blocked
        async with self.db.sessions() as session:
            user = await session.get(User, user_id)
            if (not user or user.deleted or (expected_subject is not None and user.subject != expected_subject)
                    or await provision_blocked(session, user.subject, self.settings.service_secret)):
                raise DeliveryError("account_unavailable", 409)
            subject = user.subject
        async def check(store, identifier):
            async with self.db.sessions() as session:
                return await matches_account(session, subject=subject, user_id=user_id, store=store,
                    identifier=identifier, service_secret=self.settings.service_secret)
        return subject, check

    async def apply(self, user_id, purchase, observed_at, *, generation=None, lease_token=None, expected_subject=None):
        if purchase.environment not in ("Production", "Sandbox"):
            raise DeliveryError("purchase_environment_mismatch", 400)
        if self.settings.sandbox_restricted and purchase.environment == "Sandbox" and user_id not in self.settings.store_sandbox_user_ids:
            raise DeliveryError("purchase_environment_mismatch", 400)
        # Network verification finishes before taking this lock. Older requests
        # cannot overwrite newer observations, nor transfer another user's grant.
        async with self.db.sessions.begin() as session:
            subject = expected_subject
            if subject is None:
                subject = await session.scalar(select(User.subject).where(User.id == user_id))
            if subject is None:
                raise DeliveryError("account_unavailable", 409)
            await lock_account_lifecycle(session, subject, self.settings.service_secret)
            user = (await session.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one_or_none()
            from .global_deletion import provision_blocked
            if (not user or user.deleted or user.subject != subject
                    or await provision_blocked(session, subject, self.settings.service_secret)):
                raise DeliveryError("account_unavailable", 409)
            unknown = (await session.execute(select(Entitlement).where(
                Entitlement.store == purchase.store, Entitlement.environment == "Unknown",
                Entitlement.transaction_id == purchase.transaction_id))).scalar_one_or_none()
            if unknown is not None:
                # A legacy tombstone has no proven store environment. Never resurrect it.
                raise DeliveryError("purchase_environment_mismatch", 409)
            row = (await session.execute(select(Entitlement).where(
                Entitlement.store == purchase.store, Entitlement.environment == purchase.environment, Entitlement.transaction_id == purchase.transaction_id))).scalar_one_or_none()
            if lease_token and (row is None or row.lease_token != lease_token):
                return False
            if row and row.user_id != user_id:
                raise DeliveryError("purchase_account_mismatch", 409)
            if row and row.verified_at and utc(row.verified_at) > utc(observed_at):
                return False
            if purchase.linked_transaction_id:
                previous = (await session.execute(select(Entitlement).where(
                    Entitlement.store == purchase.store, Entitlement.environment == purchase.environment,
                    Entitlement.transaction_id == purchase.linked_transaction_id))).scalar_one_or_none()
                if previous and previous.user_id != user_id:
                    raise DeliveryError("purchase_account_mismatch", 409)
                if previous:
                    previous.superseded = True
                else:
                    session.add(Entitlement(id=str(uuid4()), user_id=user_id,
                        store=purchase.store, transaction_id=purchase.linked_transaction_id,
                        product=purchase.product, environment=purchase.environment, expires_at=utc(observed_at), revoked=True, superseded=True))
            if row is None:
                row = Entitlement(id=str(uuid4()), user_id=user_id, store=purchase.store,
                                  transaction_id=purchase.transaction_id, environment=purchase.environment, superseded=False,
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
        return True

    async def sync(self, user_id, store, value, *, expected_subject=None):
        provider = self.providers.get(store)
        if not provider:
            raise DeliveryError("purchase_verification_unavailable", 503)
        subject, check = await self.ownership(user_id, expected_subject)
        observed_at = self.clock()
        purchase = await provider.verify(value, user_id, initial=True, account_check=check)
        if not await self.apply(user_id, purchase, observed_at, expected_subject=subject):
            raise DeliveryError("purchase_sync_conflict", 409)
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
            row_id, user_id, store, environment = row.id, row.user_id, row.store, row.environment
            reference = self.cipher.decrypt(row.provider_reference).decode()
        successful, expired_reference = False, False
        try:
            provider = self.providers[store]
            subject, check = await self.ownership(user_id)
            if environment == "Sandbox" and self.settings.sandbox_restricted and user_id not in self.settings.store_sandbox_user_ids:
                raise DeliveryError("purchase_environment_mismatch", 400)
            if hasattr(provider, "verify_for_environment"):
                purchase = await provider.verify_for_environment(reference, user_id, environment, account_check=check)
            else:
                purchase = await provider.verify(reference, user_id, initial=False, account_check=check)
            if purchase.environment != environment:
                raise DeliveryError("purchase_environment_mismatch", 400)
            successful = await self.apply(user_id, purchase, now, generation=generation, lease_token=token, expected_subject=subject)
            if successful:
                await provider.acknowledge(purchase)
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
        async with self.db.sessions() as session:
            user = await session.get(User, user_id)
            reviewer = user_id in self.settings.reviewer_user_ids or (
                user is not None and user.subject in self.settings.reviewer_identity_subjects)
            if user is None or user.deleted or (reviewer and user.suspended):
                raise DeliveryError("account_unavailable", 403)
            trial_start, trial_end = utc(user.cardless_trial_started_at), utc(user.cardless_trial_ends_at)
            trial_active = trial_start <= utc(now) < trial_end
            rows = (await session.execute(select(Entitlement).where(Entitlement.user_id == user_id))).scalars().all()
        if self.settings.sandbox_restricted:
            allowed = {"Production", "Sandbox"} if user_id in self.settings.store_sandbox_user_ids else {"Production"}
            rows = [r for r in rows if r.environment in allowed]
        stale_products = {r.product for r in rows if not r.revoked and not r.superseded and r.verified_at
                          and utc(r.verified_at) <= cutoff and utc(r.expires_at) > now}
        if not reviewer and not trial_active and stale_products:
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
            cardless = name == "base" and trial_active and latest is None
            result[name] = {"active": latest is not None or cardless,
                "expires_at": utc(latest.expires_at).isoformat() if latest else trial_end.isoformat() if cardless else None,
                "trial_ends_at": utc(latest.trial_ends_at).isoformat() if latest and latest.trial_ends_at and utc(latest.trial_ends_at) > now else trial_end.isoformat() if cardless else None,
                "access_source": "store" if latest else "cardless_trial" if cardless else None}
            if name == "bot_mini" and name in stale_products:
                result[name]["verification_unavailable"] = True
        result["base"]["cardless_trial"] = {"started_at": trial_start.isoformat(), "ends_at": trial_end.isoformat(), "active": trial_active}
        result["server_time"] = utc(now).isoformat()
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
            if state["bot_mini"].get("verification_unavailable"):
                raise DeliveryError("purchase_verification_unavailable", 503)
            raise DeliveryError("bot_subscription_required", 402)
        return state
