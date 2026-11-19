"""Offline quarantine/reconciliation only. This module never authorizes reopening.

Input assertions are operator-supplied evidence, not completeness attestation.
Use only an isolated copy, with API/workers stopped. No provider calls occur.
"""
from datetime import datetime
from hashlib import sha256
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, or_, select, update

from .db import (AccountDeletion, Block, BotReport, LocalBotReport, Device, Entitlement, KeyClaim,
                 ModerationAction, PendingMessage, PublicBundle, PublicPreKey,
                 PushOutbox, PushToken, RateWindow, Reservation, UsageBucket,
                 User, UserReport, VipiTrialEligibility)
from .delivery import utc


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeletionRecord(EvidenceRecord):
    # Preserve original durable receipt identities, never synthesize a credential.
    account_id: str = Field(min_length=1, max_length=36)
    subject_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    subject: str | None = Field(default=None, min_length=1, max_length=128)
    created_at: AwareDatetime
    finished_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def state(self):
        if self.finished_at is None and self.subject is None:
            raise ValueError("pending deletion needs retained identity cleanup subject")
        if self.finished_at is not None and (self.subject is not None or self.finished_at < self.created_at):
            raise ValueError("invalid completed deletion state")
        return self


class TrialEligibilityRecord(EvidenceRecord):
    subject_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    started_at: AwareDatetime
    ends_at: AwareDatetime

    @model_validator(mode="after")
    def interval(self):
        if self.ends_at < self.started_at:
            raise ValueError("invalid trial eligibility interval")
        return self


class RestrictionRecord(EvidenceRecord):
    account_id: str = Field(min_length=1, max_length=36)
    suspended: bool
    observed_at: AwareDatetime


class RecoveryEvidence(EvidenceRecord):
    schema_version: Literal[1]
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_at: AwareDatetime
    cutoff_at: AwareDatetime
    claimed_complete: bool
    deletions: list[DeletionRecord] = Field(max_length=1000)
    restrictions: list[RestrictionRecord] = Field(max_length=1000)
    trial_eligibility: list[TrialEligibilityRecord] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def interval(self):
        if self.cutoff_at < self.snapshot_at:
            raise ValueError("invalid reconciliation interval")
        for records in (self.deletions, self.restrictions):
            if len({x.account_id for x in records}) != len(records):
                raise ValueError("duplicate account evidence")
        if len({x.subject_hash for x in self.trial_eligibility}) != len(self.trial_eligibility):
            raise ValueError("duplicate trial eligibility identity")
        if any(x.started_at > self.cutoff_at for x in self.trial_eligibility):
            raise ValueError("trial eligibility exceeds supplied cutoff")
        times = [x.created_at for x in self.deletions] + [x.finished_at for x in self.deletions if x.finished_at]
        times += [x.observed_at for x in self.restrictions]
        if any(t > self.cutoff_at for t in times):
            raise ValueError("evidence exceeds supplied cutoff")
        return self


async def reconcile_offline(db, evidence: RecoveryEvidence, *, snapshot_sha256: str, now: datetime):
    """Atomically quarantine and apply only restrictive supplied evidence.

    Caller must own an isolated database. No live connection guard is claimed by
    this library; the CLI only creates a new SQLite copy. The returned report does not release either the startup hold or the
    database-local restore marker and MUST NOT be used to start API/workers.
    """
    if snapshot_sha256 != evidence.snapshot_sha256 or evidence.cutoff_at > utc(now):
        raise ValueError("snapshot binding or cutoff invalid")
    digest = sha256(evidence.model_dump_json().encode()).hexdigest()
    counts = {"deleted_accounts_present": 0, "deletion_receipts_added": 0,
              "suspensions_applied": 0, "unknown_restrictions": 0,
              "restore_requests_not_applied": 0, "trial_eligibility_added": 0}
    async with db.sessions.begin() as s:
        # Validate conflicts before any mutation; outer transaction rolls back on
        # all errors, including conflicts discovered later in the evidence list.
        for record in evidence.trial_eligibility:
            old = await s.get(VipiTrialEligibility, record.subject_hash)
            if old and (utc(old.started_at) != record.started_at or utc(old.ends_at) != record.ends_at):
                raise ValueError("conflicting trial eligibility")
            if old is None:
                s.add(VipiTrialEligibility(**record.model_dump()))
                counts["trial_eligibility_added"] += 1
        for record in evidence.deletions:
            old = await s.get(AccountDeletion, record.account_id)
            # Shared identity may have deleted/rejoined Vipi several times.
            # Distinct original account receipts must coexist without merging.
            if old and (old.subject_hash != record.subject_hash or old.receipt_hash != record.receipt_hash):
                raise ValueError("conflicting deletion receipt identity")
            user = await s.get(User, record.account_id)
            if user and record.subject is not None and user.subject != record.subject:
                raise ValueError("conflicting account subject")
            devices = select(Device.id).where(Device.user_id == record.account_id)
            for model in (PushOutbox, PushToken, PublicPreKey, PublicBundle):
                await s.execute(delete(model).where(model.device_id.in_(devices)))
            await s.execute(delete(KeyClaim).where(or_(KeyClaim.requester_device_id.in_(devices),
                KeyClaim.recipient_id == record.account_id, KeyClaim.recipient_device_id.in_(devices))))
            for model, fields in ((PendingMessage, (PendingMessage.sender_id, PendingMessage.recipient_id)),
                                  (Block, (Block.blocker_id, Block.blocked_id)),
                                  (UserReport, (UserReport.user_id, UserReport.reported_user_id))):
                await s.execute(delete(model).where(or_(*(f == record.account_id for f in fields))))
            for model in (ModerationAction, BotReport, LocalBotReport, Entitlement, Reservation, UsageBucket, Device):
                await s.execute(delete(model).where(model.user_id == record.account_id))
            if user:
                await s.execute(delete(RateWindow).where(RateWindow.subject == user.subject))
                await s.delete(user)
                counts["deleted_accounts_present"] += 1
            if old is None:
                s.add(AccountDeletion(account_id=record.account_id, subject_hash=record.subject_hash,
                    receipt_hash=record.receipt_hash, subject=record.subject,
                    created_at=record.created_at, finished_at=record.finished_at,
                    next_attempt_at=utc(now), attempts=0))
                counts["deletion_receipts_added"] += 1
            elif old.finished_at is None and record.finished_at is not None:
                old.finished_at = record.finished_at
                old.subject = None
            # Never regress an already completed deletion to pending.
        for record in evidence.restrictions:
            if not record.suspended:
                counts["restore_requests_not_applied"] += 1
                continue
            user = await s.get(User, record.account_id)
            if user is None:
                counts["unknown_restrictions"] += 1
            elif not user.suspended:
                user.suspended = True
                counts["suspensions_applied"] += 1
        await s.execute(update(Device).values(active=False))
        # Excluded transport/report content must not be resurrected even when a
        # supplied snapshot was created with the wrong table exclusions.
        for model in (PendingMessage, PublicBundle, PublicPreKey, KeyClaim,
                      PushOutbox, PushToken, UserReport, BotReport, LocalBotReport):
            await s.execute(delete(model))
        await s.execute(update(Entitlement).values(verified_at=None, lease_token=None,
            lease_until=None, next_attempt_at=utc(now)))
        await s.execute(update(AccountDeletion).values(lease_token=None, lease_until=None))
        # Keep existing charges, uncertain reservations and request IDs. Missing
        # post-snapshot requests cannot be invented or counted as unspent.
    return {"schema_version": 1, "snapshot_sha256": snapshot_sha256,
            "evidence_sha256": digest, "counts": counts,
            "claimed_complete": evidence.claimed_complete,
            "authority_verified": False, "interval_complete_verified": False,
            "reopen_authorized": False, "bot_dispatch_authorized": False,
            "runtime_gate_installed": False,
            "required_before_reopen": ["independently verified deletion/restriction interval and cutoff",
                "shared identity links and global deletion holds/receipts reconciliation",
                "billing ownership bindings and their post-snapshot global erasures reconciliation",
                "original trial eligibility interval coverage", "provider entitlement verification", "personal/global spend and consumed-request reconciliation",
                "enforced offline-to-live admission gate", "explicit native device re-enrollment"],
            "spend_policy": "retained counters/request IDs unchanged except required account erasure; global charges retained",
            "services_must_remain_stopped": True}


class CoverageRecord(EvidenceRecord):
    domain: Literal["deletions", "restrictions", "billing", "spend", "requests", "eligibility"]
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    start_at: AwareDatetime
    cutoff_at: AwareDatetime
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    claimed_complete: Literal[True]


class BoundRecoveryEvidence(EvidenceRecord):
    """Explicit external coverage claims, not an authority or a release token."""
    reconciliation: RecoveryEvidence
    coverage: list[CoverageRecord] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def coverage_binding(self):
        e = self.reconciliation
        if not e.claimed_complete:
            raise ValueError("contradictory incomplete reconciliation claim")
        if {r.domain for r in self.coverage} != {"deletions", "restrictions", "billing", "spend", "requests", "eligibility"}:
            raise ValueError("all recovery domains required exactly once")
        for row in self.coverage:
            if row.snapshot_sha256 != e.snapshot_sha256 or row.start_at != e.snapshot_at or row.cutoff_at != e.cutoff_at:
                raise ValueError("coverage must bind exact snapshot interval")
        return self


async def reconcile_marked_offline(db, supplied: BoundRecoveryEvidence, *, now: datetime):
    from .recovery_admission import require_restore_binding
    e = supplied.reconciliation
    marker = await require_restore_binding(db, e.snapshot_sha256)
    if datetime.fromisoformat(marker['snapshot_at']) != e.snapshot_at:
        raise ValueError("marker snapshot time mismatch")
    result = await reconcile_offline(db, e, snapshot_sha256=e.snapshot_sha256, now=now)
    # Neither syntactically valid assertions nor retained billing state grant
    # authority. In particular, referenced spend artifacts are not replayed.
    result.update(runtime_gate_installed=True, restore_id=marker['restore_id'],
        restore_state="HOLD", coverage_claims_supplied=True,
        coverage_claims_sha256=sha256(supplied.model_dump_json().encode()).hexdigest(),
        reconciled_domains=["deletions", "restrictions", "eligibility"],
        unapplied_domains=["billing", "spend", "requests"],
        native_reenrollment_qualified=False)
    return result
