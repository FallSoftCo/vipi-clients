"""Bounded response generation. Human chat and immersion never enter this gateway."""
import asyncio
import base64
import json
from datetime import UTC, datetime, timedelta

import httpx
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .budget import BudgetError, estimate_maximum_cost, reserve, settle
from .db import BotPool, BotReport, Reservation, UsageBucket, User
from .delivery import DeliveryError, utc

MAX_CONTEXT_BYTES = 8192
SYSTEM = "You are vBot, a friendly conversation partner in Vipi. Respond naturally and concisely in the user's language. Do not turn conversation into language lessons. Never claim to be a human or to read private chats."


def period_bounds(now):
    now = utc(now)
    reset = datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=UTC)
    return now.strftime("%Y-%m"), reset


def counted():
    return or_(Reservation.state.in_(("reserved", "uncertain")), Reservation.actual_nano_usd > 0)


async def insert_once(session, table, values):
    insert = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    await session.execute(insert(table).values(**values).on_conflict_do_nothing())


class BotGateway:
    def __init__(self, settings, db, subscriptions, clock, *, transport=None):
        self.settings, self.db, self.subscriptions, self.clock = settings, db, subscriptions, clock
        self.http = httpx.AsyncClient(timeout=60, follow_redirects=False, transport=transport)

    async def report(self, user_id, request_id, reason, selected_reply):
        if reason not in ("harmful", "inaccurate", "other") or not selected_reply.strip() or len(selected_reply.encode()) > 4000:
            raise DeliveryError("invalid_bot_report", 400)
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                   info=b"vipi-bot-report-v1").derive(self.settings.service_secret.encode())
        cipher = Fernet(base64.urlsafe_b64encode(key))
        async with self.db.sessions.begin() as session:
            user = (await session.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one_or_none()
            reservation = await session.get(Reservation, request_id)
            if not user or user.deleted or not reservation or reservation.user_id != user_id or reservation.state not in ("settled", "uncertain"):
                raise DeliveryError("bot_request_not_found", 404)
            if await session.get(BotReport, request_id) is None:
                now = self.clock()
                session.add(BotReport(request_id=request_id, user_id=user_id, reason=reason,
                    selected_reply=cipher.encrypt(selected_reply.encode()), created_at=now, expires_at=now+timedelta(days=30)))
        return {"reported": True}

    async def close(self):
        await self.http.aclose()

    async def allowance(self, user_id):
        state = await self.subscriptions.snapshot(user_id)
        period, reset = period_bounds(self.clock())
        async with self.db.sessions() as session:
            used = (await session.execute(select(func.count()).select_from(Reservation).where(
                Reservation.user_id == user_id, Reservation.period == period, counted()))).scalar_one()
        return {"period": period, "remaining_replies": max(0, self.settings.bot_monthly_replies - used),
                "monthly_replies": self.settings.bot_monthly_replies, "resets_at": reset.isoformat(),
                "available": state["bot_mini"]["available"] and bool(self.settings.deepseek_api_key),
                "service_ready": bool(self.settings.deepseek_api_key),
                "max_context_bytes": MAX_CONTEXT_BYTES}

    async def reserve_request(self, user_id, request_id, maximum):
        now = self.clock()
        period, _ = period_bounds(now)
        async with self.db.sessions.begin() as session:
            # Same user lock as deletion, then global pool, then personal bucket.
            # No provider call or plaintext is retained in this transaction.
            user = (await session.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one_or_none()
            if not user or user.deleted:
                raise DeliveryError("account_unavailable", 409)
            await insert_once(session, BotPool, {"period": period,
                "budget_nano_usd": self.settings.bot_global_monthly_budget_nano_usd,
                "reserved_nano_usd": 0, "spent_nano_usd": 0})
            pool = (await session.execute(select(BotPool).where(BotPool.period == period).with_for_update())).scalar_one()
            # Config may tighten but never silently reset already spent money.
            pool.budget_nano_usd = self.settings.bot_global_monthly_budget_nano_usd
            if pool.reserved_nano_usd + pool.spent_nano_usd + maximum > pool.budget_nano_usd:
                raise DeliveryError("bot_temporarily_unavailable", 503)
            active = select(func.count()).select_from(Reservation).where(Reservation.state == "reserved", Reservation.created_at > now - timedelta(seconds=120))
            if (await session.execute(active.where(Reservation.user_id == user_id))).scalar_one():
                raise DeliveryError("bot_reply_in_progress", 409)
            if (await session.execute(active)).scalar_one() >= 16:
                raise DeliveryError("bot_busy", 429)
            used = (await session.execute(select(func.count()).select_from(Reservation).where(
                Reservation.user_id == user_id, Reservation.period == period, counted()))).scalar_one()
            if used >= self.settings.bot_monthly_replies:
                raise DeliveryError("monthly_allowance_reached", 429)
            await insert_once(session, UsageBucket, {"user_id": user_id, "period": period,
                "budget_nano_usd": self.settings.bot_monthly_budget_nano_usd,
                "reserved_nano_usd": 0, "spent_nano_usd": 0})
            try:
                await reserve(session, user_id=user_id, request_id=request_id, maximum_cost=maximum, now=now)
            except BudgetError as error:
                raise DeliveryError(str(error), 409 if str(error) == "request_already_used" else 429) from None
            pool.reserved_nano_usd += maximum
        return period

    async def settle_request(self, request_id, period, actual_cost):
        async with self.db.sessions.begin() as session:
            # Match lock order with account deletion and reservation. Deletion
            # removes the personal record; the global reserve remains a ceiling.
            reference = await session.get(Reservation, request_id)
            if not reference:
                return
            await session.execute(select(User).where(User.id == reference.user_id).with_for_update())
            pool = (await session.execute(select(BotPool).where(BotPool.period == period).with_for_update())).scalar_one()
            item = await session.get(Reservation, request_id, populate_existing=True)
            if not item or item.state not in ("reserved", "uncertain"):
                return
            maximum = item.reserved_nano_usd
            await settle(session, request_id=request_id, actual_cost=actual_cost)
            if actual_cost is not None:
                pool.reserved_nano_usd -= maximum
                pool.spent_nano_usd += actual_cost

    async def reply(self, user_id, request_id, messages, consent_version):
        if consent_version != "deepseek-v1":
            raise DeliveryError("bot_consent_required", 400)
        if not self.settings.deepseek_api_key:
            raise DeliveryError("bot_unavailable", 503)
        if (not 1 <= len(messages) <= 12 or messages[-1]["role"] != "user"
                or any(m["role"] not in ("user", "assistant") or not m["content"].strip() for m in messages)
                or sum(len(m["content"].encode()) for m in messages) > MAX_CONTEXT_BYTES):
            raise DeliveryError("bot_context_too_large", 400)
        await self.subscriptions.require(user_id, bot=True)
        input_bytes = len(SYSTEM.encode()) + sum(len(m["content"].encode()) + 32 for m in messages)
        maximum = estimate_maximum_cost(input_bytes, self.settings.bot_output_tokens,
            input_rate=self.settings.bot_input_nano_usd_per_token, output_rate=self.settings.bot_output_nano_usd_per_token)
        period = await self.reserve_request(user_id, request_id, maximum)
        actual_cost = None
        try:
            async with asyncio.timeout(65):
                async with self.http.stream("POST", "https://api.deepseek.com/chat/completions",
                    headers={"Authorization": "Bearer " + self.settings.deepseek_api_key.get_secret_value()},
                    json={"model": self.settings.bot_model, "messages": [{"role": "system", "content": SYSTEM}, *messages],
                          "thinking": {"type": "disabled"}, "max_tokens": self.settings.bot_output_tokens, "stream": False}) as response:
                    if response.status_code in (400, 401, 402, 403, 422, 429):
                        actual_cost = 0
                        raise DeliveryError("bot_unavailable", 503)
                    if response.status_code != 200:
                        raise DeliveryError("bot_reply_unconfirmed", 503)
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 100_000:
                            raise DeliveryError("bot_reply_unconfirmed", 503)
            data = json.loads(body)
            usage = data["usage"]
            prompt, completion = usage["prompt_tokens"], usage["completion_tokens"]
            if any(type(n) is not int or n < 0 for n in (prompt, completion)):
                raise ValueError("invalid_usage")
            # Peak uncached prices bound provider spend even during off-peak or
            # cache discounts. This accounting ceiling is not a user charge.
            actual_cost = prompt * self.settings.bot_input_nano_usd_per_token + completion * self.settings.bot_output_nano_usd_per_token
            choice = data["choices"][0]
            reply = choice["message"]["content"]
            if not isinstance(reply, str) or not reply.strip() or len(reply.encode()) > 16_384 or choice.get("finish_reason") not in ("stop", "length"):
                raise ValueError("invalid_reply")
        except DeliveryError:
            raise
        except Exception:
            raise DeliveryError("bot_reply_unconfirmed", 503) from None
        finally:
            await self.settle_request(request_id, period, actual_cost)
        return {"request_id": request_id, "reply": reply, "allowance": await self.allowance(user_id)}
