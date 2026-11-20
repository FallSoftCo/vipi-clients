"""Keyed account-ownership evidence, never retained paid access or store tokens."""
import hashlib
import hmac
from uuid import UUID

from sqlalchemy import delete, select, update

from .db import BillingAccountBinding, Entitlement
from .delivery import DeliveryError
from .eligibility import eligibility_hash


def billing_account_id(user_id):
    return hashlib.sha256(("co.fallsoft.vipi:" + user_id).encode()).hexdigest()


def binding_hash(store, identifier, service_secret):
    if store == "apple":
        identifier = str(UUID(identifier))
    elif store != "google" or not isinstance(identifier, str) or not 1 <= len(identifier) <= 64:
        raise ValueError("invalid_billing_identifier")
    return hmac.new(service_secret.encode(),
        b"vipi-billing-account-v1\0" + store.encode() + b"\0" + identifier.encode(), hashlib.sha256).hexdigest()


async def retain_account(session, *, subject, user_id, service_secret):
    # The caller owns the common identity lifecycle lock. Capture even before a
    # first entitlement: store payment/approval may precede its initial sync.
    owner = eligibility_hash(subject, service_secret)
    for store, identifier in (("apple", user_id), ("google", billing_account_id(user_id))):
        # Only UUID identifiers can ever have been issued as Apple tokens.
        if store == "apple":
            try:
                UUID(identifier)
            except ValueError:
                continue
        digest = binding_hash(store, identifier, service_secret)
        row = await session.get(BillingAccountBinding, (store, digest))
        if row is None:
            session.add(BillingAccountBinding(store=store, binding_hash=digest, owner_hash=owner))
        elif not hmac.compare_digest(row.owner_hash, owner):
            raise DeliveryError("purchase_account_mismatch", 409)
    await session.flush()


async def matches_account(session, *, subject, user_id, store, identifier, service_secret):
    try:
        digest = binding_hash(store, identifier, service_secret)
        expected = user_id if store == "apple" else billing_account_id(user_id)
        current = hmac.compare_digest(digest, binding_hash(store, expected, service_secret))
    except (ValueError, TypeError, AttributeError):
        return False
    # One exact indexed lookup; no historical-id list, truncation or raw token.
    row = await session.get(BillingAccountBinding, (store, digest))
    if row is not None:
        return hmac.compare_digest(row.owner_hash, eligibility_hash(subject, service_secret))
    return current


async def transfer_account(session, *, source, target, user_id, service_secret):
    # A free profile link does not create purchase-ownership records. Preserve
    # existing historical ownership even when no paid grant remains active.
    source_owner = eligibility_hash(source, service_secret)
    prior_binding = await session.scalar(select(BillingAccountBinding.binding_hash).where(
        BillingAccountBinding.owner_hash == source_owner).limit(1))
    prior_purchase = await session.scalar(select(Entitlement.id).where(Entitlement.user_id == user_id).limit(1))
    if prior_binding is None and prior_purchase is None:
        return
    await retain_account(session, subject=source, user_id=user_id, service_secret=service_secret)
    await session.execute(update(BillingAccountBinding).where(
        BillingAccountBinding.owner_hash == eligibility_hash(source, service_secret)).values(
        owner_hash=eligibility_hash(target, service_secret)))


async def erase_accounts(session, owner_hashes):
    await session.execute(delete(BillingAccountBinding).where(BillingAccountBinding.owner_hash.in_(owner_hashes)))
