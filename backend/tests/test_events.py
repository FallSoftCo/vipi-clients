import asyncio
import os
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import update

from conftest import NOW
from test_api import TestVerifier, identity
from test_subscriptions import settings
from vipi.api import create_app
from vipi.db import Device, User
from vipi.delivery import DeliveryError, Envelope, accept, acknowledge
from vipi.events import InboxEvents, notify


class Socket:
    def __init__(self, app, headers):
        self.incoming, self.outgoing = asyncio.Queue(), asyncio.Queue()
        self.scope = {
            "type": "websocket",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "scheme": "wss",
            "path": "/v1/events",
            "raw_path": b"/v1/events",
            "query_string": b"",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": ("127.0.0.1", 1234),
            "server": ("vipi.test", 443),
            "subprotocols": [],
        }
        self.app = app

    async def __aenter__(self):
        self.incoming.put_nowait({"type": "websocket.connect"})
        self.task = asyncio.create_task(
            self.app(self.scope, self.incoming.get, self.outgoing.put)
        )
        assert (await self.next())["type"] == "websocket.accept"
        return self

    async def next(self):
        return await asyncio.wait_for(self.outgoing.get(), 5)

    async def __aexit__(self, *_):
        self.incoming.put_nowait({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(self.task, 5)


@asynccontextmanager
async def application(db, **kwargs):
    app = create_app(
        settings(**kwargs),
        database=db,
        verifier=TestVerifier(),
        clock=lambda: NOW,
        store_providers={},
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://vipi.test"
        ) as client:
            yield app, client


async def test_events_require_real_account_device_and_ignore_subscription_lapse(db):
    async with application(db) as (app, client):
        alice, device, headers = await identity(client, "alice")
        async with Socket(app, {}) as socket:
            assert (await socket.next())["code"] == 4401
        async with Socket(app, headers | {"X-Vipi-Device-Secret": "b" * 43}) as socket:
            assert (await socket.next())["code"] == 4403
        async with Socket(app, headers) as socket:
            assert (await socket.next())["text"] == '{"event":"inbox_changed"}'
            # No paid entitlement exists. A valid receiver can still drain
            # previously accepted ciphertext and read receipt status.
            app.state.events.publish(device)
            assert (await socket.next())["text"] == '{"event":"inbox_changed"}'
        assert app.state.events.count == 0
        async with db.sessions.begin() as session:
            await session.execute(
                update(Device).where(Device.id == device).values(active=False)
            )
        async with Socket(app, headers) as socket:
            assert (await socket.next())["code"] == 4403


async def test_events_are_contentless_bounded_and_reconnect_catches_up(db):
    async with application(db, foreground_connections_per_worker=1) as (app, client):
        _, device, headers = await identity(client, "alice")
        async with Socket(app, headers) as first:
            await first.next()
            async with Socket(app, headers) as excess:
                assert (await excess.next())["code"] == 1013
            # Coalescing is bounded regardless of the number of hints.
            for _ in range(100):
                app.state.events.publish(device)
            assert (await first.next())["text"] == '{"event":"inbox_changed"}'
            app.state.events.unavailable()
            assert (await first.next())["code"] == 1013
        app.state.events.ready.set()
        async with Socket(app, headers) as reconnected:
            assert (await reconnected.next())["text"] == '{"event":"inbox_changed"}'
            reconnected.incoming.put_nowait(
                {"type": "websocket.receive", "text": "never send chat text here"}
            )
            assert (await reconnected.next())["code"] == 1008
        assert app.state.events.count == 0


async def test_open_socket_revalidates_revocation_and_token(db, monkeypatch):
    monkeypatch.setattr("vipi.events.AUTH_RECHECK_SECONDS", 0.02)
    async with application(db) as (app, client):
        _, device, headers = await identity(client, "alice")
        async with Socket(app, headers) as socket:
            await socket.next()
            async with db.sessions.begin() as session:
                await session.execute(
                    update(Device).where(Device.id == device).values(active=False)
                )
            assert (await socket.next())["code"] == 4403
        async with db.sessions.begin() as session:
            await session.execute(
                update(Device).where(Device.id == device).values(active=True)
            )
        async with Socket(app, headers) as socket:
            await socket.next()
            from vipi.auth import AuthenticationError

            async def expired(_):
                raise AuthenticationError()

            monkeypatch.setattr(app.state.verifier, "verify", expired)
            assert (await socket.next())["code"] == 4401


@pytest.mark.skipif(
    not os.environ.get("VIPI_TEST_POSTGRES_URL"),
    reason="actual PostgreSQL LISTEN/NOTIFY",
)
async def test_commit_notifies_other_worker_and_rollback_does_not(db):
    first, second = InboxEvents(db), InboxEvents(db)
    await first.start()
    await second.start()
    device = str(uuid4())
    q1, q2 = first.subscribe(device), second.subscribe(device)
    q1.get_nowait()
    q2.get_nowait()
    try:
        async with db.sessions.begin() as session:
            await notify(session, device)
            assert q1.empty() and q2.empty()
        assert await asyncio.wait_for(q1.get(), 3) == "inbox_changed"
        assert await asyncio.wait_for(q2.get(), 3) == "inbox_changed"
        with pytest.raises(ValueError):
            async with db.sessions.begin() as session:
                await notify(session, device)
                raise ValueError("rollback")
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(q2.get(), 0.1)
    finally:
        first.unsubscribe(device, q1)
        second.unsubscribe(device, q2)
        await first.close()
        await second.close()


@pytest.mark.skipif(
    not os.environ.get("VIPI_TEST_POSTGRES_URL"),
    reason="actual PostgreSQL transaction signals",
)
async def test_delivery_wakes_recipient_and_receipt_wakes_sender(db):
    async with application(db) as (app, client):
        alice, ad, ah = await identity(client, "alice")
        bob, bd, bh = await identity(client, "bob")
        async with Socket(app, ah) as sender, Socket(app, bh) as recipient:
            await sender.next()
            await recipient.next()
            envelope = Envelope(
                str(uuid4()),
                alice["id"],
                ad,
                bob["id"],
                bd,
                NOW,
                b"opaque QA envelope; no real plaintext" * 2,
            )
            async with db.sessions.begin() as session:
                await accept(session, envelope, now=NOW)
            assert (await recipient.next())["text"] == '{"event":"inbox_changed"}'
            async with db.sessions.begin() as session:
                assert (
                    await acknowledge(session, envelope.id, bob["id"], bd, now=NOW)
                    == "delivered"
                )
            assert (await sender.next())["text"] == '{"event":"inbox_changed"}'


async def test_actual_websocket_protocol_ping_and_frame_limit(db):
    import socket as sockets
    import uvicorn
    from websockets.asyncio.client import connect
    from websockets.exceptions import ConnectionClosed

    async with application(db) as (app, client):
        _, _, headers = await identity(client, "alice")
        listener = sockets.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.setblocking(False)
        port = listener.getsockname()[1]
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                lifespan="off",
                ws="websockets-sansio",
                ws_max_size=512,
                ws_per_message_deflate=False,
                ws_ping_interval=0.1,
                ws_ping_timeout=1,
                access_log=False,
                log_level="critical",
            )
        )
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(5):
                while not server.started:
                    await asyncio.sleep(0.01)
            async with connect(
                f"ws://127.0.0.1:{port}/v1/events",
                additional_headers=headers,
                ping_interval=None,
            ) as ws:
                assert await ws.recv() == '{"event":"inbox_changed"}'
                await asyncio.sleep(
                    0.3
                )  # protocol ping/pong does not become application data
                await ws.send("x" * 1024)
                with pytest.raises(ConnectionClosed) as closed:
                    await ws.recv()
                assert closed.value.rcvd.code == 1009
            async with connect(
                f"ws://127.0.0.1:{port}/v1/events", ping_interval=None
            ) as invalid:
                with pytest.raises(ConnectionClosed) as closed:
                    await invalid.recv()
                assert closed.value.rcvd.code == 4401
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, 5)
            listener.close()


async def test_late_database_termination_does_not_close_replacement_listener(
    db, monkeypatch
):
    connections = []

    class Connection:
        closed = False

        def add_termination_listener(self, callback):
            self.terminated = callback

        async def add_listener(self, *_):
            pass

        def is_closed(self):
            return self.closed

        async def close(self, **_):
            self.closed = True

    async def connect(*_, **__):
        value = Connection()
        connections.append(value)
        return value

    monkeypatch.setattr("vipi.events.asyncpg.connect", connect)
    broker = InboxEvents(db)
    broker.task = asyncio.create_task(broker.listen())
    try:
        await asyncio.wait_for(broker.ready.wait(), 3)
        old = connections[0]
        old.closed = True
        old.terminated(old)
        async with asyncio.timeout(3):
            while len(connections) < 2 or not broker.ready.is_set():
                await asyncio.sleep(0.01)
        old.terminated(old)  # delayed callback from an earlier connection
        await asyncio.sleep(0.03)
        assert (
            len(connections) == 2
            and not connections[1].closed
            and broker.ready.is_set()
        )
    finally:
        await broker.close()


async def test_events_and_http_reject_old_shared_auth_time_for_new_profile_floor(db):
    async with application(db) as (app, client):
        alice, _, headers = await identity(client, "alice")
        async with db.sessions.begin() as session:
            await session.execute(
                update(User)
                .where(User.id == alice["id"])
                .values(minimum_auth_time=int(NOW.timestamp()) + 1)
            )
        assert (await client.get("/v1/me", headers=headers)).status_code == 401
        async with Socket(app, headers) as socket:
            assert (await socket.next())["code"] == 4403
        assert app.state.events.count == 0
