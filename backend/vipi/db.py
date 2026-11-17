from datetime import datetime, timedelta
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String, BigInteger, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject: Mapped[str] = mapped_column(String(128), unique=True)
    minimum_auth_time: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    username: Mapped[str] = mapped_column(String(24), unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cardless_trial_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda ctx: ctx.get_current_parameters()["created_at"])
    cardless_trial_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda ctx: ctx.get_current_parameters()["created_at"] + timedelta(days=30))
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    suspended: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    credential_hash: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PendingMessage(Base):
    __tablename__ = "pending_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sender_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    recipient_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    sender_device_id: Mapped[str] = mapped_column(String(36))
    recipient_device_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    cipher_type: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default="accepted")
    __table_args__ = (Index("inbox_pending", "recipient_device_id", "state", "accepted_at"),)


class Block(Base):
    __tablename__ = "blocks"
    blocker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    blocked_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)


class PublicBundle(Base):
    __tablename__ = "public_bundles"
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    registration_id: Mapped[int] = mapped_column(Integer)
    identity_key: Mapped[bytes] = mapped_column(LargeBinary)
    signed_key_id: Mapped[int] = mapped_column(Integer)
    signed_key: Mapped[bytes] = mapped_column(LargeBinary)
    signed_signature: Mapped[bytes] = mapped_column(LargeBinary)
    revision: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(64))
    high_key_id: Mapped[int] = mapped_column(Integer)


class PublicPreKey(Base):
    __tablename__ = "public_prekeys"
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    key_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ec_key: Mapped[bytes] = mapped_column(LargeBinary)
    kem_key: Mapped[bytes] = mapped_column(LargeBinary)
    kem_signature: Mapped[bytes] = mapped_column(LargeBinary)


class KeyClaim(Base):
    __tablename__ = "key_claims"
    requester_device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    recipient_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    recipient_device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    response: Mapped[bytes] = mapped_column(LargeBinary)


class Entitlement(Base):
    __tablename__ = "entitlements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    product: Mapped[str] = mapped_column(String(32))
    store: Mapped[str] = mapped_column(String(16))
    transaction_id: Mapped[str] = mapped_column(String(256))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)
    provider_reference: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    refresh_generation: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    completed_generation: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("store", "environment", "transaction_id", name="uq_entitlements_store_environment_transaction"),)


class BillingNotification(Base):
    __tablename__ = "billing_notifications"
    store: Mapped[str] = mapped_column(String(8), primary_key=True)
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class UsageBucket(Base):
    __tablename__ = "usage_buckets"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    period: Mapped[str] = mapped_column(String(7), primary_key=True)
    budget_nano_usd: Mapped[int] = mapped_column(BigInteger)
    reserved_nano_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    spent_nano_usd: Mapped[int] = mapped_column(BigInteger, default=0)


class Reservation(Base):
    __tablename__ = "bot_reservations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    period: Mapped[str] = mapped_column(String(7))
    reserved_nano_usd: Mapped[int] = mapped_column(BigInteger)
    actual_nano_usd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    state: Mapped[str] = mapped_column(String(20), default="reserved")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BotPool(Base):
    __tablename__ = "bot_pools"
    period: Mapped[str] = mapped_column(String(7), primary_key=True)
    budget_nano_usd: Mapped[int] = mapped_column(BigInteger)
    reserved_nano_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    spent_nano_usd: Mapped[int] = mapped_column(BigInteger, default=0)


class BotReport(Base):
    __tablename__ = "bot_reports"
    request_id: Mapped[str] = mapped_column(ForeignKey("bot_reservations.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    reason: Mapped[str] = mapped_column(String(16))
    selected_reply: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class UserReport(Base):
    __tablename__ = "user_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    reported_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    payload: Mapped[bytes] = mapped_column(LargeBinary)
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(128), nullable=True)


class ModerationAction(Base):
    __tablename__ = "moderation_actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    operator: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PushToken(Base):
    __tablename__ = "push_tokens"
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    provider: Mapped[str] = mapped_column(String(8))
    environment: Mapped[str] = mapped_column(String(16))
    fingerprint: Mapped[str] = mapped_column(String(64))
    token: Mapped[bytes] = mapped_column(LargeBinary)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("provider", "environment", "fingerprint"),)


class PushOutbox(Base):
    __tablename__ = "push_outbox"
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    generation: Mapped[int] = mapped_column(BigInteger)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RateWindow(Base):
    __tablename__ = "rate_windows"
    subject: Mapped[str] = mapped_column(String(128), primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), primary_key=True)
    window: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    count: Mapped[int] = mapped_column(Integer)


class VipiTrialEligibility(Base):
    """Original trial dates only, retained across app-only delete/rejoin."""
    __tablename__ = "vipi_trial_eligibility"
    subject_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AccountDeletion(Base):
    """Bounded durable cleanup receipt, independent of the removed user row."""
    __tablename__ = "account_deletions"
    account_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject_hash: Mapped[str] = mapped_column(String(64), index=True)
    receipt_hash: Mapped[str] = mapped_column(String(64))
    subject: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Database:
    def __init__(self, url: str, *, connect_args=None, offline_recovery=False):
        self.engine = create_async_engine(url, pool_pre_ping=True, connect_args=connect_args or {})
        self.offline_recovery = offline_recovery
        if not offline_recovery:
            from .recovery_admission import install_admission
            install_admission(self.engine)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def check_admission(self):
        async with self.engine.connect():
            pass

    async def create_for_test(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def close(self):
        await self.engine.dispose()
