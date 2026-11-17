"""Privacy-minimal original Base trial dates; never a paid entitlement transfer."""
import hashlib
import hmac
from datetime import timedelta

from .db import VipiTrialEligibility
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
    record = await session.get(VipiTrialEligibility, eligibility_hash(subject, service_secret))
    if record is not None:
        await session.delete(record)
