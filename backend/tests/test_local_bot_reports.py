import json
import secrets
from uuid import uuid4

import pytest
from sqlalchemy import select

from conftest import NOW
from test_api import api, identity
from vipi.db import LocalBotReport, Reservation, User
from vipi.deletion import request_deletion
from vipi.delivery import DeliveryError
from vipi.local_bot_reports import submit
from vipi.reports import report_cipher

SECRET = "a" * 43


def report(**changes):
    return (
        dict(
            report_id=str(uuid4()),
            provider="gemini-nano",
            reason="inaccurate",
            selected_reply="A selected reply only.",
            consent_version="local-bot-report-v1",
        )
        | changes
    )


async def save(db, value, user="alice"):
    async with db.sessions.begin() as session:
        return await submit(session, user_id=user, secret=SECRET, now=NOW, **value)


async def test_selected_reply_is_encrypted_idempotent_without_purchase_or_generation(
    db,
):
    value = report()
    expected = {"reported": True, "report_id": value["report_id"]}
    assert await save(db, value) == expected
    assert await save(db, value) == expected
    async with db.sessions() as s:
        stored = await s.get(LocalBotReport, value["report_id"])
        assert value["selected_reply"].encode() not in stored.payload
        assert (stored.expires_at - stored.created_at).days == 30
        assert json.loads(
            report_cipher(SECRET, local_bot=True).decrypt(stored.payload)
        ) == {k: v for k, v in value.items() if k != "report_id"}
        assert list((await s.execute(select(Reservation))).scalars()) == []
    for change in [
        {"reason": "other"},
        {"selected_reply": "Changed"},
        {"provider": "apple-foundation-models"},
    ]:
        with pytest.raises(DeliveryError, match="report_id_conflict"):
            await save(db, value | change)
    with pytest.raises(DeliveryError, match="report_id_conflict"):
        await save(db, value, "bob")


@pytest.mark.parametrize(
    "change,code",
    [
        ({"consent_version": "deepseek-v1"}, "report_consent_required"),
        ({"provider": "deepseek"}, "invalid_bot_report"),
        ({"reason": "spam"}, "invalid_bot_report"),
        ({"selected_reply": " \n "}, "invalid_bot_report"),
        ({"selected_reply": "日" * 1334}, "invalid_bot_report"),
        ({"selected_reply": "\ud800"}, "invalid_bot_report"),
    ],
)
async def test_invalid_consent_or_payload_never_retained(db, change, code):
    with pytest.raises(DeliveryError, match=code):
        await save(db, report(**change))
    async with db.sessions() as s:
        assert list((await s.execute(select(LocalBotReport))).scalars()) == []


async def test_report_bound_daily_and_removed_by_account_deletion(db):
    first = report()
    await save(db, first)
    for _ in range(19):
        await save(db, report())
    # The exact retry does not consume a new stored report, even at the cap.
    assert (await save(db, first))["reported"]
    with pytest.raises(DeliveryError, match="report_limit_reached"):
        await save(db, report())
    async with db.sessions.begin() as s:
        await request_deletion(
            s,
            subject="user_alice",
            account_id="alice",
            receipt_secret=secrets.token_urlsafe(32),
            service_secret=SECRET,
            now=NOW,
        )
    async with db.sessions() as s:
        assert list((await s.execute(select(LocalBotReport))).scalars()) == []
    with pytest.raises(DeliveryError, match="account_unavailable"):
        await save(db, report())


async def test_suspended_reporter_cannot_submit(db):
    async with db.sessions.begin() as s:
        (await s.get(User, "alice")).suspended = True
    with pytest.raises(DeliveryError, match="account_unavailable"):
        await save(db, report())


async def test_disabled_endpoint_never_retains_selected_reply(api, db):
    value = report()
    path = "/v1/bot/local-reports"
    assert (await api.post(path, json=value)).status_code == 401
    _, _, headers = await identity(api, "alice")
    for body in (value, value | {"consent_version": ""}, value):
        result = await api.post(path, headers=headers, json=body)
        assert result.status_code == 410 and result.json() == {
            "error": "bot_unavailable"
        }
    async with db.sessions() as session:
        assert not (await session.scalars(select(LocalBotReport))).all()
