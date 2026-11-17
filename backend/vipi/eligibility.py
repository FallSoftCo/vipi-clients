"""Privacy-minimal original Base trial dates; never a paid entitlement transfer."""
import hashlib
import hmac
from datetime import timedelta
from sqlalchemy import delete, select

from .db import VipiTrialEligibility, VipiTrialEligibilityLink
from .delivery import utc


def eligibility_hash(subject: str, service_secret: str) -> str:
    return hmac.new(service_secret.encode(), b"vipi-trial-eligibility-v1\0" + subject.encode(), hashlib.sha256).hexdigest()


async def original_trial(session, *, subject: str, service_secret: str, started_at, ends_at=None):
    key = eligibility_hash(subject, service_secret)
    record = await session.get(VipiTrialEligibility, key)
    if record is None:
        record = VipiTrialEligibility(subject_hash=key, started_at=utc(started_at),
            ends_at=utc(ends_at) if ends_at is not None else utc(started_at) + timedelta(days=30))
        session.add(record)
        await session.flush()
    return record


async def erase_for_global_fallsoft_deletion(session, *, subject: str, service_secret: str):
    """Integration hook for an independently authorized central deletion workflow.

    Vipi app-only deletion MUST NOT call this. Calling the hook does not erase
    other apps or delete the shared identity; no central workflow is implemented.
    """
    # A central adapter receives a verified raw shared user ID. Convert it using
    # identity_authorities.canonical_shared_subject before calling this hook.
    key = eligibility_hash(subject, service_secret)
    aliases = (await session.scalars(select(VipiTrialEligibilityLink).where(
        VipiTrialEligibilityLink.target_hash == key))).all()
    keys = {key, *(alias.source_hash for alias in aliases)}
    await session.execute(delete(VipiTrialEligibilityLink).where(VipiTrialEligibilityLink.target_hash == key))
    await session.execute(delete(VipiTrialEligibility).where(VipiTrialEligibility.subject_hash.in_(keys)))


async def transfer_original_trial(session, *, source: str, target: str, user, service_secret: str):
    """A verified link preserves the earliest eligibility of both identities."""
    old = await original_trial(session, subject=source, service_secret=service_secret,
        started_at=user.cardless_trial_started_at, ends_at=user.cardless_trial_ends_at)
    new = await original_trial(session, subject=target, service_secret=service_secret,
        started_at=old.started_at, ends_at=old.ends_at)
    started = min(utc(old.started_at), utc(new.started_at), utc(user.cardless_trial_started_at))
    ends = min(utc(old.ends_at), utc(new.ends_at), utc(user.cardless_trial_ends_at))
    old.started_at = new.started_at = user.cardless_trial_started_at = started
    old.ends_at = new.ends_at = user.cardless_trial_ends_at = ends
    pair = (old.subject_hash, new.subject_hash)
    if await session.get(VipiTrialEligibilityLink, pair) is None:
        session.add(VipiTrialEligibilityLink(source_hash=pair[0], target_hash=pair[1]))
