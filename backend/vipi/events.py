"""Contentless foreground inbox hints; durable delivery stays in HTTPS APIs."""
import asyncio
import logging
import json
import time
from collections import OrderedDict, defaultdict
from uuid import UUID

import asyncpg
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select, text

from .accounts import active_device
from .auth import AuthenticationError
from .db import User
from .delivery import DeliveryError
from .rates import consume

CHANNEL = "vipi_inbox_events"
AUTH_RECHECK_SECONDS = 25
logger = logging.getLogger(__name__)


async def notify(session, device_id):
    # PostgreSQL emits only after the enclosing transaction commits. Rollback
    # cannot cause phantom delivery. Payload is an opaque device UUID only.
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(text("SELECT pg_notify(:channel, :device)"), {"channel":CHANNEL, "device":device_id})


async def notify_chat(session, device_id, event):
    if session.get_bind().dialect.name == "postgresql":
        payload = json.dumps({"device": device_id, **event}, separators=(",", ":"))
        await session.execute(text("SELECT pg_notify(:channel, :payload)"),
                              {"channel": CHANNEL, "payload": payload})


class EventQueue:
    """One coalesced hint per event/peer, with a bounded per-socket backlog."""
    def __init__(self, chat_events=False):
        self.chat_events = chat_events
        self.maxsize = 32 if chat_events else 1
        self.pending = OrderedDict()
        self.available = asyncio.Event()

    def empty(self):
        return not self.pending

    def put_nowait(self, event):
        if (None, None) in self.pending:
            return
        if event is None:
            self.pending.clear()
            key = (None, None)
        elif isinstance(event, dict):
            if not self.chat_events:
                return
            key = (event["event"], event["peer"])
        else:
            key = (event, None)
        if key not in self.pending and len(self.pending) >= self.maxsize:
            # Typing is ephemeral; prefer keeping durable catch-up hints.
            transient = next((k for k in self.pending if k[0] == "typing"), None)
            if transient is None and key[0] == "typing":
                return
            victim = transient or next((k for k in self.pending if k[0] == "receipts_changed"), None)
            if victim is None:
                return
            del self.pending[victim]
        self.pending[key] = event
        self.available.set()

    def get_nowait(self):
        if self.empty():
            raise asyncio.QueueEmpty
        _, event = self.pending.popitem(last=False)
        if self.empty():
            self.available.clear()
        return event

    async def get(self):
        while self.empty():
            await self.available.wait()
        return self.get_nowait()


class InboxEvents:
    def __init__(self, db, *, limit=200):
        self.db, self.limit = db, limit
        self.subscribers = defaultdict(set)
        self.count = 0
        self.ready = asyncio.Event()
        self.task = None

    def publish(self, device_id, event="inbox_changed"):
        for queue in self.subscribers.get(device_id, ()):
            queue.put_nowait(event)

    def dispatch(self, payload):
        if not payload.startswith("{"):
            self.publish(payload)
            return
        try:
            value = json.loads(payload)
            device = value.pop("device")
            if str(UUID(device)) != device or str(UUID(value["peer"])) != value["peer"]:
                return
            kind = value.get("event")
            if kind == "typing":
                if set(value) != {"event", "peer", "active"} or type(value["active"]) is not bool:
                    return
            elif kind == "receipts_changed":
                if set(value) != {"event", "peer"}:
                    return
            else:
                return
        except (ValueError, KeyError, TypeError, AttributeError):
            return
        self.publish(device, value)

    def subscribe(self, device_id, *, chat_events=False):
        if not self.ready.is_set() or self.count >= self.limit or len(self.subscribers.get(device_id, ())) >= 2:
            raise DeliveryError("events_unavailable", 503)
        queue = EventQueue(chat_events)
        self.subscribers[device_id].add(queue)
        self.count += 1
        queue.put_nowait("inbox_changed")  # catch up after any missed connection
        return queue

    def unsubscribe(self, device_id, queue):
        if queue in self.subscribers.get(device_id, ()):
            self.subscribers[device_id].remove(queue)
            self.count -= 1
            if not self.subscribers[device_id]:
                del self.subscribers[device_id]

    def unavailable(self):
        self.ready.clear()
        for queues in self.subscribers.values():
            for queue in queues:
                if not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)

    async def start(self):
        if self.db.engine.dialect.name != "postgresql":
            # SQLite is confined to development/unit tests by Settings.
            self.ready.set()
            return
        self.task = asyncio.create_task(self.listen())
        try:
            await asyncio.wait_for(self.ready.wait(), 12)
        except BaseException:
            await self.close()
            raise

    async def close(self):
        self.unavailable()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    async def listen(self):
        delay = 1
        while True:
            connection = None
            try:
                # asyncpg uses the same socket/credentials as the ORM. Never
                # log the DSN or an exception that could contain credentials.
                dsn = self.db.engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
                connection = await asyncpg.connect(dsn, timeout=8, command_timeout=8)
                ended = asyncio.Event()
                connection.add_termination_listener(lambda _, done=ended: done.set())
                await connection.add_listener(CHANNEL, lambda _c, _pid, _channel, payload: self.dispatch(payload))
                self.ready.set()
                delay = 1
                await ended.wait()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Foreground inbox listener reconnecting")
            finally:
                self.unavailable()
                if connection and not connection.is_closed():
                    await connection.close(timeout=5)
            await asyncio.sleep(delay)
            delay = min(30, delay * 2)


def install(app, settings, db, verifier, now, broker):
    async def validate(socket):
        bearer = socket.headers.get("Authorization", "")
        if not bearer.startswith("Bearer "):
            raise AuthenticationError()
        principal = await verifier.verify(bearer[7:])
        if settings.allowed_subjects and principal.subject not in settings.allowed_subjects:
            raise DeliveryError("service_not_available", 403)
        device_id = socket.headers.get("X-Vipi-Device-ID", "")
        try:
            if str(UUID(device_id)) != device_id:
                raise ValueError()
        except ValueError:
            raise DeliveryError("device_revoked", 403)
        async with db.sessions() as session:
            from .global_deletion import provision_blocked
            if await provision_blocked(session, principal.subject, settings.service_secret):
                raise DeliveryError("account_deleted", 403)
            user = (await session.execute(select(User).where(User.subject == principal.subject,
                User.deleted.is_(False), User.suspended.is_(False)))).scalar_one_or_none()
            if not user:
                raise DeliveryError("account_unavailable", 403)
            if principal.authenticated_at < user.minimum_auth_time:
                raise DeliveryError("recent_sign_in_required", 401)
            try:
                await active_device(session, user.id, device_id, socket.headers.get("X-Vipi-Device-Secret", ""),
                    service_secret=settings.service_secret)
            except DeliveryError:
                raise DeliveryError("device_revoked", 403) from None
        return principal, device_id, user.id

    @app.websocket("/v1/events")
    async def events(socket: WebSocket):
        queue = receive = pending = None
        device_id = None
        # Accept only the protocol handshake before reporting an explicit close
        # reason; no inbox data is sent until bearer and device checks succeed.
        await socket.accept()
        try:
            principal, device_id, user_id = await validate(socket)
            async with db.sessions.begin() as session:
                await consume(session, subject=principal.subject, scope="events", now=now().timestamp(), limit=30)
            queue = broker.subscribe(device_id, chat_events=socket.headers.get("X-Vipi-Chat-Events") == "1")
            receive = asyncio.create_task(socket.receive())
            checked = time.monotonic()
            while True:
                pending = asyncio.create_task(queue.get())
                ready, _ = await asyncio.wait((receive, pending), timeout=max(0, AUTH_RECHECK_SECONDS-(time.monotonic()-checked)),
                    return_when=asyncio.FIRST_COMPLETED)
                if receive in ready:
                    event = receive.result()
                    if event["type"] != "websocket.disconnect":
                        await socket.close(code=1008)  # protocol is server→client hints only
                    return
                if time.monotonic()-checked >= AUTH_RECHECK_SECONDS:
                    await validate(socket)
                    checked = time.monotonic()
                if pending in ready:
                    event = pending.result()
                    if event is None:
                        await socket.close(code=1013)
                        return
                    if isinstance(event, dict):
                        # Fresh authorization prevents queued hints disclosing
                        # typing/read activity after blocking or device change.
                        _, _, user_id = await validate(socket)
                        from .chat_events import event_visible
                        async with db.sessions() as session:
                            if not await event_visible(session, user_id, device_id, event, now=now()):
                                continue
                        payload = event
                    else:
                        payload = {"event": event}
                    await asyncio.wait_for(socket.send_json(payload), 5)
                else:
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
                pending = None
        except AuthenticationError:
            await socket.close(code=4401)
        except DeliveryError as error:
            await socket.close(code=4403 if error.status in (401,403,404) else 1013)
        except WebSocketDisconnect:
            pass
        except Exception as error:
            logger.warning("Foreground socket closed: %s", type(error).__name__)
            try:
                await socket.close(code=1013)
            except (RuntimeError, OSError, WebSocketDisconnect):
                pass
        finally:
            for task in (receive, pending):
                if task:
                    task.cancel()
            await asyncio.gather(*(t for t in (receive,pending) if t), return_exceptions=True)
            if queue is not None:
                broker.unsubscribe(device_id, queue)
