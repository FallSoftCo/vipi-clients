from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String, BigInteger, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject: Mapped[str] = mapped_column(String(128), unique=True)
    username: Mapped[str] = mapped_column(String(24), unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)


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
    fingerprint: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default="accepted")
    __table_args__ = (Index("inbox_pending", "recipient_device_id", "state", "accepted_at"),)


class Block(Base):
    __tablename__ = "blocks"
    blocker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    blocked_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)


class Entitlement(Base):
    __tablename__ = "entitlements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    product: Mapped[str] = mapped_column(String(32))
    store: Mapped[str] = mapped_column(String(16))
    transaction_id: Mapped[str] = mapped_column(String(256))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("store", "transaction_id"),)


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


class RateWindow(Base):
    __tablename__ = "rate_windows"
    subject: Mapped[str] = mapped_column(String(128), primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), primary_key=True)
    window: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    count: Mapped[int] = mapped_column(Integer)


class Database:
    def __init__(self, url: str, *, connect_args=None):
        self.engine = create_async_engine(url, pool_pre_ping=True, connect_args=connect_args or {})
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_for_test(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def close(self):
        await self.engine.dispose()
