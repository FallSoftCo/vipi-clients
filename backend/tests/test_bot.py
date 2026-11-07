from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from conftest import NOW
from vipi.bot import BotGateway
from vipi.db import BotPool, Reservation, UsageBucket
from vipi.delivery import DeliveryError
from vipi.subscriptions import Subscriptions
from test_subscriptions import purchase, settings


async def gateway(db, handler, **config):
    options = settings(deepseek_api_key="fixture-key", **config)
    subscriptions = Subscriptions(options, db, {}, lambda: NOW)
    await subscriptions.apply("alice", purchase(), NOW)
    await subscriptions.apply("alice", purchase("bot_mini", transaction_id="bot"), NOW)
    return BotGateway(options, db, subscriptions, lambda: NOW, transport=httpx.MockTransport(handler))


def response():
    return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "Hello!"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 10}})


async def test_response_budget_binding_and_duplicate_do_not_repeat_provider(db):
    calls = []
    async def handler(request):
        import json
        body = json.loads(request.content)
        assert body["thinking"] == {"type": "disabled"} and body["max_tokens"] == 384
        assert "tools" not in body
        calls.append(body)
        return response()
    bot = await gateway(db, handler)
    try:
        request_id = str(uuid4())
        result = await bot.reply("alice", request_id, [{"role": "user", "content": "Hi"}], "deepseek-v1")
        assert result["reply"] == "Hello!" and result["allowance"]["remaining_replies"] == 149
        with pytest.raises(DeliveryError, match="request_already_used"):
            await bot.reply("alice", request_id, [{"role": "user", "content": "Hi"}], "deepseek-v1")
        assert len(calls) == 1
        async with db.sessions() as session:
            record = await session.get(Reservation, request_id)
            pool = await session.get(BotPool, "2026-10")
            assert record.actual_nano_usd == 42_000 and pool.spent_nano_usd == 42_000
            assert pool.reserved_nano_usd == 0
    finally:
        await bot.close()


@pytest.mark.parametrize("outcome", ["timeout", "malformed", "server_error"])
async def test_uncertain_outcome_keeps_spend_reserved_and_does_not_retry(db, outcome):
    calls = []
    def handler(request):
        calls.append(1)
        if outcome == "timeout":
            raise httpx.ReadTimeout("fixture contains private text; must never escape")
        if outcome == "malformed":
            return httpx.Response(200, text="provider text must not escape")
        return httpx.Response(500)
    bot = await gateway(db, handler)
    try:
        request_id = str(uuid4())
        with pytest.raises(DeliveryError, match="bot_reply_unconfirmed"):
            await bot.reply("alice", request_id, [{"role": "user", "content": "Hi"}], "deepseek-v1")
        with pytest.raises(DeliveryError, match="request_already_used"):
            await bot.reply("alice", request_id, [{"role": "user", "content": "Hi"}], "deepseek-v1")
        assert len(calls) == 1
        async with db.sessions() as session:
            record = await session.get(Reservation, request_id)
            pool = await session.get(BotPool, "2026-10")
            assert record.state == "uncertain" and pool.reserved_nano_usd == record.reserved_nano_usd > 0
    finally:
        await bot.close()


async def test_consent_entitlement_and_input_limits_precede_provider(db):
    calls = []
    def handler(request):
        calls.append(1)
        return response()
    bot = await gateway(db, handler)
    try:
        with pytest.raises(DeliveryError, match="bot_consent_required"):
            await bot.reply("alice", str(uuid4()), [{"role": "user", "content": "Hi"}], "wrong-version")
        with pytest.raises(DeliveryError, match="base_subscription_required"):
            await bot.reply("bob", str(uuid4()), [{"role": "user", "content": "Hi"}], "deepseek-v1")
        with pytest.raises(DeliveryError, match="bot_context_too_large"):
            await bot.reply("alice", str(uuid4()), [{"role": "user", "content": "日"*3000}], "deepseek-v1")
        assert not calls
    finally:
        await bot.close()


async def test_global_spend_ceiling_prevents_dispatch(db):
    calls = []
    bot = await gateway(db, lambda request: calls.append(1) or response(), bot_global_monthly_budget_nano_usd=1)
    try:
        with pytest.raises(DeliveryError, match="bot_temporarily_unavailable"):
            await bot.reply("alice", str(uuid4()), [{"role": "user", "content": "Hi"}], "deepseek-v1")
        assert not calls
    finally:
        await bot.close()


async def test_definite_rejection_releases_budget_and_monthly_quantity(db):
    bot = await gateway(db, lambda request: httpx.Response(429))
    try:
        with pytest.raises(DeliveryError, match="bot_unavailable"):
            await bot.reply("alice", str(uuid4()), [{"role": "user", "content": "Hi"}], "deepseek-v1")
        assert (await bot.allowance("alice"))["remaining_replies"] == 150
        async with db.sessions() as session:
            assert (await session.get(BotPool, "2026-10")).reserved_nano_usd == 0
    finally:
        await bot.close()


async def test_reports_are_request_bound_idempotent_encrypted_and_deleted_with_account(db):
    import secrets
    from vipi.db import BotReport
    from vipi.deletion import request_deletion
    bot = await gateway(db, lambda request: response())
    try:
        request_id = str(uuid4())
        await bot.reply("alice", request_id, [{"role": "user", "content": "Hi"}], "deepseek-v1")
        assert await bot.report("alice", request_id, "inaccurate", "Hello!") == {"reported": True}
        await bot.report("alice", request_id, "other", "ignored retry")
        with pytest.raises(DeliveryError, match="bot_request_not_found"):
            await bot.report("bob", request_id, "harmful", "foreign report")
        with pytest.raises(DeliveryError, match="invalid_bot_report"):
            await bot.report("alice", request_id, "other", "日"*1400)
        async with db.sessions() as session:
            report = await session.get(BotReport, request_id)
            assert report.reason == "inaccurate" and b"Hello!" not in report.selected_reply
            assert (report.expires_at - report.created_at).days == 30
        async with db.sessions.begin() as session:
            await request_deletion(session, subject="user_alice", account_id="alice",
                receipt_secret=secrets.token_urlsafe(32), service_secret="a"*43, now=NOW)
        async with db.sessions() as session:
            assert await session.get(BotReport, request_id) is None
    finally:
        await bot.close()
