import asyncio
import secrets
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text

from conftest import NOW
from test_api import TestVerifier, identity
from test_deletion import settings
from vipi.api import PRICE_SURVEY, create_app
from vipi.db import Base, SurveyDecision

URL = "/v1/me/surveys/private-chat-usd1-v1"


@pytest_asyncio.fixture
async def api(db):
    app = create_app(
        settings(), database=db, verifier=TestVerifier(), clock=lambda: NOW
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://vipi.test"
    ) as client:
        yield client


async def test_private_price_question_requires_a_profile_and_a_valid_choice(api):
    assert (await api.get(URL)).status_code == 401
    assert (await api.put(URL, json={"choice": "yes"})).status_code == 401
    assert (
        await api.get(URL, headers={"Authorization": "Bearer alice"})
    ).status_code == 404
    _, _, headers = await identity(api, "alice")
    for payload in (
        {},
        {"choice": "five stars"},
        {"choice": "yes", "message": "private"},
    ):
        response = await api.put(URL, json=payload, headers=headers)
        assert response.status_code == 422
        assert response.json() == {"error": "invalid_request"}
    response = await api.get(URL, headers=headers)
    assert response.json() == {"available": True}
    assert "no-store" in response.headers["cache-control"]
    assert (await api.get("/v1/me/surveys/unknown", headers=headers)).status_code == 404


async def test_single_choice_survives_retries_and_only_own_account_can_erase_it(
    api, db
):
    alice, _, alice_headers = await identity(api, "alice")
    _, _, bob_headers = await identity(api, "bob")
    for choice in ("no", "no", "yes"):
        response = await api.put(URL, headers=alice_headers, json={"choice": choice})
        assert response.status_code == 204 and response.content == b""
    assert (await api.get(URL, headers=alice_headers)).json() == {"available": False}
    assert (await api.get(URL, headers=bob_headers)).json() == {"available": True}
    assert (
        await api.put(URL, headers=bob_headers, json={"choice": "skip"})
    ).status_code == 204
    assert (await api.get(URL, headers=bob_headers)).json() == {"available": False}

    async def counts():
        async with db.sessions() as session:
            grouped = select(SurveyDecision.choice, func.count()).group_by(
                SurveyDecision.choice
            )
            return dict((await session.execute(grouped)).all())

    assert await counts() == {"no": 1, "skip": 1}
    body = {"account_id": alice["id"], "receipt_secret": secrets.token_urlsafe(32)}
    assert (
        await api.request("DELETE", "/v1/me", json=body, headers=alice_headers)
    ).status_code == 202
    assert await counts() == {"skip": 1}
    assert (
        await api.put(URL, headers=alice_headers, json={"choice": "yes"})
    ).status_code == 404


async def test_two_concurrent_devices_share_one_decision(api, db):
    account, _, headers = await identity(api, "alice")
    responses = await asyncio.gather(
        *(
            api.put(URL, headers=headers, json={"choice": choice})
            for choice in ("maybe", "yes")
        )
    )
    assert [response.status_code for response in responses] == [204, 204]
    async with db.sessions() as session:
        row = await session.get(SurveyDecision, (account["id"], PRICE_SURVEY))
        assert row.choice in {"maybe", "yes"}
        assert (
            await session.scalar(select(func.count()).select_from(SurveyDecision)) == 1
        )


async def test_upgrade_keeps_existing_profile_and_downgrade_keeps_its_answer(db):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))

    def migrate(connection, action, revision):
        config.attributes["connection"] = connection
        action(config, revision)

    async with db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(migrate, command.upgrade, "20261121_02")
        await connection.execute(
            text(
                "INSERT INTO users (id, subject, username, display_name, created_at, deleted,"
                " cardless_trial_started_at, cardless_trial_ends_at) VALUES"
                " ('old','user_old','old','Old',:now,false,:now,:now)"
            ),
            {"now": NOW},
        )
        await connection.run_sync(migrate, command.upgrade, "head")
    async with db.sessions.begin() as session:
        assert await session.get(SurveyDecision, ("old", PRICE_SURVEY)) is None
        session.add(
            SurveyDecision(user_id="old", campaign=PRICE_SURVEY, choice="maybe")
        )
    with pytest.raises(RuntimeError, match="Preserve existing survey decisions"):
        async with db.engine.begin() as connection:
            await connection.run_sync(migrate, command.downgrade, "20261121_02")
    async with db.sessions() as session:
        assert (
            await session.get(SurveyDecision, ("old", PRICE_SURVEY))
        ).choice == "maybe"
