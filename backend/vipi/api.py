import base64
import binascii
import time
import unicodedata
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import and_, or_, select, text
from sqlalchemy.exc import IntegrityError
from starlette.responses import JSONResponse

from .accounts import active_device, normalize_username, register_device, set_block
from .auth import AuthenticationError, Principal, WorkOSVerifier
from .config import Settings
from .db import Block, Database, Device, PendingMessage, User
from .delivery import DeliveryError, Envelope, accept, acknowledge, utc
from .rates import consume


class BodyLimit:
    def __init__(self, app, limit=100_000):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        data = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            data.extend(event.get("body", b""))
            if len(data) > self.limit:
                return await JSONResponse({"error": "request_too_large"}, status_code=413)(scope, receive, send)
            if not event.get("more_body", False):
                break
        consumed = False
        async def replay():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": bytes(data), "more_body": False}
            return await receive()
        await self.app(scope, replay, send)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileInput(Input):
    username: str = Field(min_length=3, max_length=24)
    display_name: str = Field(min_length=1, max_length=80)

    @field_validator("display_name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value or any(unicodedata.category(c).startswith("C") for c in value):
            raise ValueError("invalid_name")
        return value


class DeviceInput(Input):
    device_id: UUID
    secret: str = Field(min_length=43, max_length=43, repr=False)
    replace_active: bool = False


class SendInput(Input):
    id: UUID
    recipient_id: UUID
    recipient_device_id: UUID
    created_at: AwareDatetime
    ciphertext: str = Field(min_length=44, max_length=87_384, repr=False)


class BlockInput(Input):
    blocked: bool


def profile(user):
    return {"id": user.id, "username": user.username, "display_name": user.display_name}


def message_status(item):
    return {"id": item.id, "state": item.state, "expires_at": utc(item.expires_at).isoformat()}


async def principal(request: Request, authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("sign_in_required")
    return await request.app.state.verifier.verify(authorization[7:])


def create_app(settings: Settings, *, database=None, verifier=None, clock=None):
    db = database or Database(settings.database_url)
    token_verifier = verifier or WorkOSVerifier(settings)
    now = clock or (lambda: datetime.now(UTC))

    @asynccontextmanager
    async def lifespan(app):
        yield
        if verifier is None:
            await token_verifier.close()
        if database is None:
            await db.close()

    app = FastAPI(title="Vipi service", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(BodyLimit)
    app.state.verifier = token_verifier

    @app.exception_handler(AuthenticationError)
    async def auth_error(request, error):
        return JSONResponse({"error": "sign_in_required"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})

    @app.exception_handler(DeliveryError)
    async def delivery_error(request, error):
        return JSONResponse({"error": error.code}, status_code=error.status,
            headers={"Retry-After": "60"} if error.status == 429 else {})

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, error):
        # Default validation responses echo input, which may contain credentials.
        return JSONResponse({"error": "invalid_request"}, status_code=422)

    async def user_for(session, p: Principal):
        user = (await session.execute(select(User).where(User.subject == p.subject, User.deleted.is_(False)))).scalar_one_or_none()
        if not user:
            raise DeliveryError("profile_required", 404)
        return user

    async def phone_for(session, request, user):
        device_id = request.headers.get("X-Vipi-Device-ID", "")
        try:
            if str(UUID(device_id)) != device_id:
                raise ValueError()
        except ValueError:
            raise DeliveryError("device_revoked", 401)
        return await active_device(session, user.id, device_id, request.headers.get("X-Vipi-Device-Secret", ""), service_secret=settings.service_secret)

    async def rate(p, scope, limit):
        # Commit independently: rejected requests must still consume their budget.
        async with db.sessions.begin() as session:
            await consume(session, subject=p.subject, scope=scope, now=now().timestamp(), limit=limit)

    @app.get("/health/live")
    async def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready():
        async with db.sessions() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/v1/me")
    async def me(p: Annotated[Principal, Depends(principal)]):
        await rate(p, "profile", 60)
        async with db.sessions() as session:
            return profile(await user_for(session, p))

    @app.put("/v1/me")
    async def create_profile(body: ProfileInput, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "registration", 10)
        username = normalize_username(body.username)
        try:
            async with db.sessions.begin() as session:
                user = (await session.execute(select(User).where(User.subject == p.subject).with_for_update())).scalar_one_or_none()
                if user:
                    if user.deleted:
                        raise DeliveryError("account_unavailable", 409)
                    if user.username != username:
                        raise DeliveryError("profile_already_exists", 409)
                else:
                    user = User(id=str(uuid4()), subject=p.subject, username=username, display_name=body.display_name, created_at=now())
                    session.add(user)
                    await session.flush()
                return profile(user)
        except IntegrityError:
            raise DeliveryError("username_unavailable", 409)

    @app.post("/v1/devices")
    async def device(body: DeviceInput, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "device-registration", 10)
        if not 0 <= now().timestamp() - p.authenticated_at <= 600:
            raise DeliveryError("recent_sign_in_required", 401)
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            value = await register_device(session, user_id=user.id, device_id=str(body.device_id), secret=body.secret,
                replace_active=body.replace_active, service_secret=settings.service_secret, now=now())
            return {"id": value.id, "active": value.active}

    @app.get("/v1/people/{username}")
    async def find_person(username: str, request: Request, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "exact-lookup", 30)
        name = normalize_username(username)
        async with db.sessions() as session:
            user = await user_for(session, p)
            await phone_for(session, request, user)
            other = (await session.execute(select(User).where(User.username == name, User.deleted.is_(False)))).scalar_one_or_none()
            if not other:
                raise DeliveryError("person_not_found", 404)
            block = (await session.execute(select(Block).where(or_(
                and_(Block.blocker_id == user.id, Block.blocked_id == other.id),
                and_(Block.blocker_id == other.id, Block.blocked_id == user.id))))).first()
            if block:
                raise DeliveryError("person_not_found", 404)
            return profile(other)

    @app.post("/v1/messages")
    async def send(body: SendInput, request: Request, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "send", 120)
        try:
            ciphertext = base64.b64decode(body.ciphertext, validate=True)
        except (ValueError, binascii.Error):
            raise DeliveryError("invalid_ciphertext")
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            device = await phone_for(session, request, user)
            value = await accept(session, Envelope(str(body.id), user.id, device.id, str(body.recipient_id),
                str(body.recipient_device_id), body.created_at, ciphertext), now=now(),
                max_bytes=settings.max_message_bytes, max_pending=settings.max_pending_per_recipient)
            return message_status(value)

    @app.get("/v1/messages/pending")
    async def pending(request: Request, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "inbox", 120)
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            await session.execute(select(User).where(User.id == user.id).with_for_update())
            device = await phone_for(session, request, user)
            items = (await session.execute(select(PendingMessage).where(PendingMessage.recipient_device_id == device.id,
                PendingMessage.state == "accepted", PendingMessage.expires_at > now()).order_by(PendingMessage.accepted_at, PendingMessage.id).limit(100))).scalars().all()
            return {"messages": [message_status(item) | {"sender_id": item.sender_id, "sender_device_id": item.sender_device_id,
                "recipient_device_id": item.recipient_device_id, "created_at": utc(item.created_at).isoformat(),
                "ciphertext": base64.b64encode(item.ciphertext).decode()} for item in items]}

    @app.get("/v1/messages/{message_id}")
    async def status(message_id: UUID, request: Request, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "status", 120)
        async with db.sessions() as session:
            user = await user_for(session, p)
            device = await phone_for(session, request, user)
            item = await session.get(PendingMessage, str(message_id))
            if not item or item.sender_id != user.id or item.sender_device_id != device.id:
                raise DeliveryError("message_not_found", 404)
            result = message_status(item)
            if item.state == "accepted" and utc(item.expires_at) <= now():
                result["state"] = "expired"
            return result

    @app.post("/v1/messages/{message_id}/receipt")
    async def receipt(message_id: UUID, request: Request, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "receipt", 240)
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            device = await phone_for(session, request, user)
            state = await acknowledge(session, str(message_id), user.id, device.id, now=now())
            return {"id": str(message_id), "state": state}

    @app.put("/v1/blocks/{user_id}")
    async def block(user_id: UUID, body: BlockInput, request: Request, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "blocking", 30)
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            await phone_for(session, request, user)
            await set_block(session, blocker_id=user.id, blocked_id=str(user_id), blocked=body.blocked)
            return {"blocked": body.blocked}

    return app


def application():
    return create_app(Settings())
