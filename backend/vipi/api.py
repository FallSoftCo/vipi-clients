import base64
import binascii
import unicodedata
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, StrictBool, field_validator
from sqlalchemy import and_, delete, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from starlette.responses import JSONResponse, Response

from .accounts import active_device, normalize_username, register_device, set_block, visible_peer_device
from .auth import AuthenticationError, FixedVerifierSet, Principal, WorkOSVerifier
from .config import Settings
from .db import Block, Database, PendingMessage, PushOutbox, PushToken, SurveyDecision, User
from .delivery import CHAT_FEATURE_LEASE, DeliveryError, Envelope, accept, acknowledge, chat_features_version, utc
from .rates import consume
from .prekeys import PublishInput, claim, inventory, publish
from .inbox import message_status, pending_page
from .deletion import deletion_for, deletion_status, request_deletion, subject_hash, lock_account_lifecycle


class BodyLimit:
    def __init__(self, app, limit=100_000, *, groups_enabled=False, media_limit=0):
        self.app = app
        self.limit = limit
        self.groups_enabled = groups_enabled
        self.media_limit = media_limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if self.media_limit and scope.get("method") == "PUT":
            parts = scope.get("path", "").split("/")
            if len(parts) == 5 and parts[1:3] == ["v1", "media"] and parts[4] == "ciphertext":
                try:
                    canonical = str(UUID(parts[3])) == parts[3]
                except ValueError:
                    canonical = False
                if canonical:
                    total = 0
                    async def bounded():
                        nonlocal total
                        event = await receive(); total += len(event.get("body", b""))
                        if total > self.media_limit:
                            raise DeliveryError("media_too_large", 413)
                        return event
                    return await self.app(scope, bounded, send)
        limit = 1_500_000 if self.groups_enabled and scope.get("path", "").startswith("/v1/groups/") else self.limit
        data = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            data.extend(event.get("body", b""))
            if len(data) > limit:
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


class DeleteAccountInput(Input):
    account_id: UUID
    receipt_secret: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


class IdentityLinkInput(Input):
    request_id: UUID
    expected_account_id: UUID
    fallsoft_access_token: SecretStr = Field(min_length=1, max_length=16_384, repr=False)


class DeviceInput(Input):
    device_id: UUID
    secret: str = Field(min_length=43, max_length=43, repr=False)
    replace_active: bool = False


class ChatFeaturesInput(Input):
    version: int = Field(strict=True, ge=0, le=1)


class SendInput(Input):
    required_chat_features_version: int = Field(default=0, strict=True, ge=0, le=1)
    id: UUID
    recipient_id: UUID
    recipient_device_id: UUID
    created_at: AwareDatetime
    cipher_type: Literal[2, 3]
    ciphertext: str = Field(min_length=44, max_length=87_384, repr=False)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=8)


class TypingInput(Input):
    active: StrictBool


PRICE_SURVEY = "private-chat-usd1-v1"


class SurveyInput(Input):
    choice: Literal["yes", "maybe", "no", "skip"]


class ReceiptsInput(Input):
    seen: list[UUID] = Field(default_factory=list, max_length=64)
    check: list[UUID] = Field(default_factory=list, max_length=64)


class BlockInput(Input):
    blocked: bool


class ClaimInput(Input):
    request_id: UUID


class ApplePurchaseInput(Input):
    signed_transaction_info: str = Field(min_length=20, max_length=30_000, repr=False)


class GooglePurchaseInput(Input):
    purchase_token: str = Field(min_length=1, max_length=4096, repr=False)


class BotMessageInput(Input):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8192, repr=False)


class BotInput(Input):
    request_id: UUID
    consent_version: str = Field(max_length=32)
    messages: list[BotMessageInput] = Field(min_length=1, max_length=12)


class NotificationEnvelopeInput(Input):
    ticket: str = Field(min_length=80, max_length=1024)


class PushInput(Input):
    provider: Literal["fcm", "apns"]
    environment: Literal["production", "sandbox"]
    token: str = Field(min_length=20, max_length=4096, repr=False)


class BotReportInput(Input):
    request_id: UUID
    reason: Literal["harmful", "inaccurate", "other"]
    selected_reply: str = Field(min_length=1, max_length=4000, repr=False)


class LocalBotReportInput(Input):
    report_id: UUID
    provider: Literal["gemini-nano", "apple-foundation-models"]
    reason: Literal["harmful", "inaccurate", "other"]
    selected_reply: str = Field(min_length=1, max_length=4000, repr=False)
    consent_version: str = Field(max_length=32)


class UserReportInput(Input):
    report_id: UUID
    reported_user_id: UUID
    message_id: UUID | None = None
    reason: Literal["spam", "harassment", "harmful", "other"]
    selected_text: str | None = Field(default=None, max_length=32768, repr=False)
    consent_version: str = Field(max_length=32)


def profile(user):
    return {"id": user.id, "username": user.username, "display_name": user.display_name}


async def verified_principal(request: Request, authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("sign_in_required")
    return await request.app.state.verifier.verify(authorization[7:])


async def principal(request: Request, verified: Annotated[Principal, Depends(verified_principal)]):
    allowed = request.app.state.allowed_subjects
    if allowed and verified.subject not in allowed:
        raise DeliveryError("service_not_available", 403)
    return verified


def create_app(settings: Settings, *, database=None, verifier=None, clock=None, web_provider_transport=None,
               store_providers=None, bot_transport=None, notification_transport=None, shared_verifier=None):
    if settings.recovery_hold:
        from .recovery_gate import held_application
        return held_application()
    if settings.environment == "staging" and not settings.allowed_subjects:
        raise ValueError("Staging requires an explicit verified-subject allowlist")
    db = database or Database(settings.database_url)
    primary_verifier = verifier or WorkOSVerifier(settings)
    token_verifier = primary_verifier
    owned_verifiers = [primary_verifier] if verifier is None else []
    link_verifier = None
    if settings.shared_identity_transition_enabled:
        from .identity_authorities import FALLSOFT_VIPI, LEGACY_VIPI
        if shared_verifier is not None:
            link_verifier = shared_verifier
        elif settings.workos_client_id == FALLSOFT_VIPI.client_id:
            link_verifier = primary_verifier
        else:
            link_verifier = WorkOSVerifier(settings, authority=FALLSOFT_VIPI)
            owned_verifiers.append(link_verifier)
        if settings.workos_client_id == FALLSOFT_VIPI.client_id:
            legacy = WorkOSVerifier(settings, authority=LEGACY_VIPI)
            owned_verifiers.append(legacy)
            token_verifier = FixedVerifierSet(primary_verifier, legacy)
        else:
            token_verifier = FixedVerifierSet(primary_verifier, link_verifier)
    now = clock or (lambda: datetime.now(UTC))
    from .subscriptions import Subscriptions
    from .bot import BotGateway
    # No new purchases in the free product. Historical reconciliation belongs
    # to its separate worker; the chat API never opens a store provider.
    providers = {} if store_providers is None else store_providers
    subscriptions = Subscriptions(settings, db, providers, now)
    bot = BotGateway(settings, db, subscriptions, now, transport=bot_transport)
    from .events import InboxEvents, install as install_events
    events = InboxEvents(db, limit=settings.foreground_connections_per_worker)

    @asynccontextmanager
    async def lifespan(app):
        try:
            if isinstance(db, Database):
                await db.check_admission()
            await events.start()
            yield
        finally:
            await events.close()
            await bot.close()
            await app.state.pubsub_verifier.close()
            if store_providers is None:
                for provider in providers.values():
                    await provider.close()
            for owned in owned_verifiers:
                await owned.close()
            if database is None:
                await db.close()

    app = FastAPI(title="Vipi service", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(
        BodyLimit,
        groups_enabled=settings.groups_enabled,
        media_limit=settings.media_max_bytes if settings.media_enabled else 0,
    )
    app.state.verifier = token_verifier
    app.state.allowed_subjects = settings.allowed_subjects
    app.state.subscriptions = subscriptions
    app.state.bot = bot
    app.state.events = events
    install_events(app, settings, db, token_verifier, now, events)
    from .web_deletion import install as install_web_deletion
    install_web_deletion(app, settings, db, token_verifier, now, provider_transport=web_provider_transport)
    from .global_deletion import install as install_global_deletion
    install_global_deletion(app, settings, db, now)
    from .public_pages import install as install_public_pages
    install_public_pages(app)
    from .store_notifications import install as install_store_notifications
    install_store_notifications(app, settings, db, subscriptions, now, google_transport=notification_transport)

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

    async def user_for(session, p: Principal, *, allow_restricted=False):
        from .global_deletion import provision_blocked
        if await provision_blocked(session, p.subject, settings.service_secret):
            raise DeliveryError("account_deleted", 403)
        user = (await session.execute(select(User).where(User.subject == p.subject, User.deleted.is_(False)))).scalar_one_or_none()
        if not user:
            raise DeliveryError("profile_required", 404)
        if p.authenticated_at < user.minimum_auth_time:
            raise DeliveryError("recent_sign_in_required", 401)
        if user.suspended and not allow_restricted:
            raise DeliveryError("account_restricted", 403)
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

    from .media import install as install_media
    install_media(app, settings, db, principal, user_for, phone_for, rate, now)

    @app.get("/health/live")
    async def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready():
        async with db.sessions() as session:
            await session.execute(text("SELECT 1"))
            if settings.environment in {"staging", "production"}:
                if not events.ready.is_set():
                    return JSONResponse({"status": "events_unavailable"}, status_code=503)
                revisions = (await session.scalars(text("SELECT version_num FROM alembic_version"))).all()
                if revisions != ["20261126_01"]:
                    return JSONResponse({"status": "schema_unavailable"}, status_code=503)
        return {"status": "ok"}

    def own_profile(user):
        response = profile(user)
        version = settings.group_protocol_for(user.id)
        if version is not None:
            response["group_protocol_version"] = version
        return JSONResponse(response, headers={"Cache-Control": "private, no-store"})

    def reads_groups(request, user):
        return request.headers.get("X-Vipi-Group-Protocol") == "1" and settings.group_protocol_for(user.id) == 1

    @app.get("/v1/me")
    async def me(p: Annotated[Principal, Depends(principal)]):
        await rate(p, "profile", 60)
        async with db.sessions() as session:
            return own_profile(await user_for(session, p))

    @app.get(f"/v1/me/surveys/{PRICE_SURVEY}")
    async def survey_availability(p: Annotated[Principal, Depends(principal)]):
        await rate(p, "survey", 30)
        async with db.sessions() as session:
            user = await user_for(session, p)
            decision = await session.get(SurveyDecision, (user.id, PRICE_SURVEY))
        return JSONResponse({"available": decision is None}, headers={"Cache-Control": "private, no-store"})

    @app.put(f"/v1/me/surveys/{PRICE_SURVEY}", status_code=204)
    async def survey_decide(body: SurveyInput, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "survey", 30)
        async with db.sessions.begin() as session:
            await lock_account_lifecycle(session, p.subject, settings.service_secret)
            user = await user_for(session, p)
            insert = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
            statement = insert(SurveyDecision).values(user_id=user.id, campaign=PRICE_SURVEY, choice=body.choice)
            await session.execute(statement.on_conflict_do_nothing(index_elements=["user_id", "campaign"]))
        return Response(status_code=204, headers={"Cache-Control": "private, no-store"})

    @app.get("/v1/entitlements")
    async def entitlements(p: Annotated[Principal, Depends(principal)]):
        await rate(p, "entitlements", 30)
        async with db.sessions() as session:
            user = await user_for(session, p, allow_restricted=True)
        # Ordinary chat stays free. Previously verified add-ons keep their
        # original verification and expiry rules without initiating a store call.
        state = await subscriptions.snapshot(user.id, free_base=True)
        return JSONResponse(state, headers={"Cache-Control": "private, no-store", "Vary": "Authorization"})

    async def purchase_sync(p, store, credential):
        raise DeliveryError("purchases_unavailable", 410)

    @app.post("/v1/purchases/apple")
    async def apple_purchase(body: ApplePurchaseInput, p: Annotated[Principal, Depends(principal)]):
        return await purchase_sync(p, "apple", body.signed_transaction_info)

    @app.post("/v1/purchases/google")
    async def google_purchase(body: GooglePurchaseInput, p: Annotated[Principal, Depends(principal)]):
        return await purchase_sync(p, "google", body.purchase_token)

    @app.get("/v1/bot/allowance")
    async def bot_allowance(p: Annotated[Principal, Depends(principal)]):
        raise DeliveryError("bot_unavailable", 410)

    @app.post("/v1/bot/messages")
    async def bot_message(body: BotInput, request: Request, p: Annotated[Principal, Depends(principal)]):
        raise DeliveryError("bot_unavailable", 410)

    @app.post("/v1/bot/reports", status_code=202)
    async def bot_report(body: BotReportInput, request: Request, p: Annotated[Principal, Depends(principal)]):
        raise DeliveryError("bot_unavailable", 410)

    @app.post("/v1/bot/local-reports", status_code=202)
    async def local_bot_report(body: LocalBotReportInput, request: Request,
                               p: Annotated[Principal, Depends(principal)]):
        raise DeliveryError("bot_unavailable", 410)

    @app.post("/v1/reports", status_code=202)
    async def user_report(body: UserReportInput, request: Request, p: Annotated[Principal, Depends(principal)]):
        from .reports import submit
        await rate(p, "user-reports", 5)
        try:
            async with db.sessions.begin() as session:
                user = await user_for(session, p)
                await phone_for(session, request, user)
                return await submit(session, user_id=user.id, report_id=str(body.report_id),
                    reported_user_id=str(body.reported_user_id),
                    message_id=str(body.message_id) if body.message_id else None,
                    reason=body.reason, selected_text=body.selected_text,
                    consent_version=body.consent_version, secret=settings.service_secret, now=now())
        except IntegrityError:
            raise DeliveryError("report_id_conflict", 409) from None

    @app.put("/v1/me")
    async def create_profile(body: ProfileInput, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "registration", 10)
        username = normalize_username(body.username)
        try:
            async with db.sessions.begin() as session:
                await lock_account_lifecycle(session, p.subject, settings.service_secret)
                from .global_deletion import provision_blocked
                if await provision_blocked(session, p.subject, settings.service_secret):
                    raise DeliveryError("account_deleted", 409)
                from .identity_linking import source_was_linked
                if await source_was_linked(session, p.subject, settings.service_secret):
                    raise DeliveryError("fallsoft_sign_in_required", 409)
                user = (await session.execute(select(User).where(User.subject == p.subject).with_for_update())).scalar_one_or_none()
                deletion = await deletion_for(session, p.subject, settings.service_secret)
                if deletion and deletion.finished_at is None:
                    raise DeliveryError("account_deletion_pending", 409)
                if deletion and p.authenticated_at <= utc(deletion.created_at).timestamp():
                    raise DeliveryError("recent_sign_in_required", 401)
                if user:
                    if p.authenticated_at < user.minimum_auth_time:
                        raise DeliveryError("recent_sign_in_required", 401)
                    if user.deleted:
                        raise DeliveryError("account_unavailable", 409)
                    if user.suspended:
                        raise DeliveryError("account_restricted", 403)
                    if user.username != username:
                        raise DeliveryError("profile_already_exists", 409)
                else:
                    # A shared refresh session must not silently recreate a
                    # deleted Vipi profile after its seven-day receipt expires.
                    if not 0 <= now().timestamp() - p.authenticated_at <= 600:
                        raise DeliveryError("recent_sign_in_required", 401)
                    created = now()
                    user = User(id=str(uuid4()), subject=p.subject, minimum_auth_time=p.authenticated_at,
                        username=username, display_name=body.display_name, created_at=created,
                        cardless_trial_started_at=created, cardless_trial_ends_at=created)
                    session.add(user)
                    await session.flush()
                return own_profile(user)
        except IntegrityError:
            raise DeliveryError("username_unavailable", 409)

    @app.post("/v1/identity-links/fallsoft")
    async def link_fallsoft_identity(body: IdentityLinkInput, request: Request,
                                     p: Annotated[Principal, Depends(principal)]):
        if not settings.shared_identity_transition_enabled or link_verifier is None:
            raise DeliveryError("identity_link_unavailable", 404)
        from .identity_linking import link_identity
        await rate(p, "identity-link", 5)
        shared = await link_verifier.verify(body.fallsoft_access_token.get_secret_value())
        try:
            async with db.sessions.begin() as session:
                return await link_identity(session, source=p, target=shared,
                    request_id=str(body.request_id), account_id=str(body.expected_account_id),
                    device_id=request.headers.get("X-Vipi-Device-ID", ""),
                    device_secret=request.headers.get("X-Vipi-Device-Secret", ""),
                    service_secret=settings.service_secret, now=now())
        except IntegrityError:
            raise DeliveryError("identity_link_conflict", 409) from None

    @app.delete("/v1/me", status_code=202)
    async def delete_account(body: DeleteAccountInput, p: Annotated[Principal, Depends(verified_principal)]):
        if not settings.account_deletion_enabled:
            raise DeliveryError("account_deletion_unavailable", 503)
        if not 0 <= now().timestamp() - p.authenticated_at <= 600:
            raise DeliveryError("recent_sign_in_required", 401)
        await rate(p, "account-deletion", 10)
        async with db.sessions.begin() as session:
            job = await request_deletion(session, subject=p.subject, account_id=str(body.account_id),
                                         receipt_secret=body.receipt_secret, service_secret=settings.service_secret, now=now(), authenticated_at=p.authenticated_at)
            return {"account_id": job.account_id, "status": "deleted" if job.finished_at else "deletion_requested"}

    @app.get("/v1/account-deletions/{account_id}")
    async def account_deletion_status(account_id: UUID, request: Request, authorization: Annotated[str | None, Header()] = None):
        # Client creates and durably saves this 256-bit capability BEFORE sending
        # DELETE. Polling survives Vipi deletion and a lost response.
        if not authorization or not authorization.startswith("Deletion "):
            raise DeliveryError("deletion_receipt_unavailable", 404)
        remote = request.client.host if request.client else "unknown"
        async with db.sessions.begin() as session:
            await consume(session, subject="delete-status:" + subject_hash(remote, settings.service_secret),
                          scope="deletion-status", now=now().timestamp(), limit=120)
        async with db.sessions() as session:
            return await deletion_status(session, account_id=str(account_id), receipt_secret=authorization[9:], service_secret=settings.service_secret)

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

    @app.put("/v1/devices/chat-features")
    async def advertise_chat_features(body: ChatFeaturesInput, request: Request, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "chat-features-register", 60)
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            # Both device replacement and direct/group admission take this same user lock.
            await session.execute(select(User.id).where(User.id == user.id).with_for_update())
            device = await phone_for(session, request, user)
            version = body.version if settings.chat_features_enabled else 0
            device.chat_features_v1_until = now() + CHAT_FEATURE_LEASE if version else None
            return {"version": version, "device_id": device.id}

    @app.get("/v1/people/{peer_id}/chat-features")
    async def peer_chat_features(peer_id: UUID, request: Request, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "chat-features-read", 120)
        async with db.sessions() as session:
            user = await user_for(session, p)
            await phone_for(session, request, user)
            device = await visible_peer_device(session, user.id, str(peer_id))
            version = chat_features_version(device, now()) if settings.chat_features_enabled else 0
            return JSONResponse({"version": version, "device_id": device.id if device else None},
                                headers={"Cache-Control": "private, no-store"})

    @app.put("/v1/devices/push")
    async def register_push(body: PushInput, request: Request, p: Annotated[Principal, Depends(principal)]):
        from .push import register
        await rate(p, "push-registration", 10)
        try:
            async with db.sessions.begin() as session:
                user = await user_for(session, p)
                device = await phone_for(session, request, user)
                await register(session, user_id=user.id, device_id=device.id, provider=body.provider,
                    environment=body.environment, token=body.token, secret=settings.service_secret, now=now())
            return {"registered": True}
        except IntegrityError:
            raise DeliveryError("push_registration_conflict", 409) from None

    @app.delete("/v1/devices/push")
    async def unregister_push(request: Request, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "push-registration", 10)
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            await session.execute(select(User).where(User.id == user.id).with_for_update())
            device = await phone_for(session, request, user)
            await session.execute(delete(PushOutbox).where(PushOutbox.device_id == device.id))
            await session.execute(delete(PushToken).where(PushToken.device_id == device.id))
        return {"registered": False}

    @app.get("/v1/people/by-id/{peer_id}")
    async def peer_profile(peer_id: UUID, request: Request, p: Annotated[Principal, Depends(principal)]):
        # Incoming encrypted envelopes identify the sender by opaque account ID.
        # Resolve display metadata without exposing email or implying key trust.
        await rate(p, "peer-profile", 30)
        async with db.sessions() as session:
            user = await user_for(session, p)
            await phone_for(session, request, user)
            other = await session.get(User, str(peer_id))
            if not other or other.deleted or other.suspended:
                raise DeliveryError("recipient_unavailable", 404)
            blocked = (await session.execute(select(Block).where(or_(
                and_(Block.blocker_id == user.id, Block.blocked_id == other.id),
                and_(Block.blocker_id == other.id, Block.blocked_id == user.id))))).first()
            if blocked:
                raise DeliveryError("recipient_unavailable", 404)
            return profile(other)

    @app.get("/v1/people/{username}")
    async def find_person(username: str, request: Request, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "exact-lookup", 30)
        name = normalize_username(username)
        async with db.sessions() as session:
            user = await user_for(session, p)
            await phone_for(session, request, user)
            other = (await session.execute(select(User).where(User.username == name, User.deleted.is_(False), User.suspended.is_(False)))).scalar_one_or_none()
            if not other:
                raise DeliveryError("person_not_found", 404)
            block = (await session.execute(select(Block).where(or_(
                and_(Block.blocker_id == user.id, Block.blocked_id == other.id),
                and_(Block.blocker_id == other.id, Block.blocked_id == user.id))))).first()
            if block:
                raise DeliveryError("person_not_found", 404)
            return profile(other)

    @app.put("/v1/keys")
    async def publish_keys(body: PublishInput, request: Request, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "key-publication", 30)
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            device = await phone_for(session, request, user)
            return await publish(session, user_id=user.id, device_id=device.id, body=body)

    @app.get("/v1/keys")
    async def own_keys(request: Request, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "key-inventory", 30)
        async with db.sessions() as session:
            user = await user_for(session, p)
            device = await phone_for(session, request, user)
            return await inventory(session, device.id)

    @app.post("/v1/people/{recipient_id}/keys")
    async def claim_keys(recipient_id: UUID, body: ClaimInput, request: Request, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "key-claim", 30)
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            device = await phone_for(session, request, user)
            return await claim(session, user_id=user.id, device_id=device.id, recipient_id=str(recipient_id),
                request_id=str(body.request_id), now=now())

    @app.post("/v1/messages")
    async def send(body: SendInput, request: Request, p: Annotated[Principal, Depends(principal)]):
        if body.attachment_ids and not settings.media_enabled:
            raise DeliveryError("media_unavailable", 404)
        if len(set(body.attachment_ids)) != len(body.attachment_ids):
            raise DeliveryError("invalid_media_references")
        await rate(p, "send", 120)
        # Every authenticated, unrestricted account can send. No trial clock,
        # receipt, purchase provider or billing outage participates in delivery.
        try:
            ciphertext = base64.b64decode(body.ciphertext, validate=True)
        except (ValueError, binascii.Error):
            raise DeliveryError("invalid_ciphertext")
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            device = await phone_for(session, request, user)
            value = await accept(session, Envelope(str(body.id), user.id, device.id, str(body.recipient_id),
                str(body.recipient_device_id), body.created_at, ciphertext, body.cipher_type,
                tuple(str(ident) for ident in body.attachment_ids), body.required_chat_features_version), now=now(),
                max_bytes=settings.max_message_bytes, max_pending=settings.max_pending_per_recipient,
                media_draining=settings.media_draining, chat_features_enabled=settings.chat_features_enabled)
            if value.state == "accepted" and not value.required_chat_features_version and not (body.attachment_ids and settings.media_draining):
                from .push import enqueue
                await enqueue(session, value.recipient_device_id, now(), value.expires_at)
            return message_status(value)

    @app.post("/v1/notifications/envelope")
    async def notification_envelope(body: NotificationEnvelopeInput, request: Request):
        from .push import preview_envelope
        async with db.sessions.begin() as session:
            item = await preview_envelope(session, ticket=body.ticket,
                device_id=request.headers.get("X-Vipi-Device-ID", ""),
                device_secret=request.headers.get("X-Vipi-Device-Secret", ""), secret=settings.service_secret, now=now())
            await consume(session, subject=request.headers["X-Vipi-Device-ID"], scope="notification-envelope", now=now().timestamp(), limit=120)
            return JSONResponse(item, headers={"Cache-Control": "no-store"})

    @app.get("/v1/messages/pending")
    async def pending(request: Request, response: Response, p: Annotated[Principal, Depends(principal)], after: Annotated[str | None, Query(max_length=512)] = None):
        response.headers["Cache-Control"] = "private, no-store"
        await rate(p, "inbox", 120)
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            await session.execute(select(User).where(User.id == user.id).with_for_update())
            device = await phone_for(session, request, user)
            return await pending_page(
                session, device, now=now(), after=after, secret=settings.service_secret,
                reads_chat_features=request.headers.get("X-Vipi-Chat-Features") == "1",
                reads_groups=reads_groups(request, user),
            )

    @app.get("/v1/messages/{message_id}")
    async def status(message_id: UUID, request: Request, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "status", 120)
        async with db.sessions() as session:
            user = await user_for(session, p)
            device = await phone_for(session, request, user)
            item = await session.get(PendingMessage, str(message_id))
            if not item or item.sender_id != user.id or item.sender_device_id != device.id or (not item.is_direct and not reads_groups(request, user)):
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
            state = await acknowledge(session, str(message_id), user.id, device.id, now=now(), allow_groups=reads_groups(request, user))
            return {"id": str(message_id), "state": state}

    @app.post("/v1/conversations/{peer_id}/typing")
    async def typing_event(peer_id: UUID, body: TypingInput, request: Request,
                           p: Annotated[Principal, Depends(principal)]):
        await rate(p, "chat-typing", 60)
        from .chat_events import typing
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            device = await phone_for(session, request, user)
            await typing(session, user.id, device.id, str(peer_id), body.active, now=now())
        return {"accepted": True}

    @app.post("/v1/conversations/{peer_id}/receipts")
    async def conversation_receipts(peer_id: UUID, body: ReceiptsInput, request: Request,
                                    p: Annotated[Principal, Depends(principal)]):
        await rate(p, "chat-receipts", 240)
        from .chat_events import receipts
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            device = await phone_for(session, request, user)
            return await receipts(session, user.id, device.id, str(peer_id),
                [str(item) for item in body.seen], [str(item) for item in body.check], now=now())

    @app.get("/v1/blocks/{user_id}")
    async def block_status(user_id: UUID, request: Request, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "block-status", 60)
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            await phone_for(session, request, user)
            # Only reveal this account's own choice, never whether someone
            # else blocked it or whether an arbitrary account exists.
            return {"blocked": await session.get(Block, (user.id, str(user_id))) is not None}

    @app.put("/v1/blocks/{user_id}")
    async def block(user_id: UUID, body: BlockInput, request: Request, p: Annotated[Principal, Depends(principal)]):
        await rate(p, "blocking", 30)
        async with db.sessions.begin() as session:
            user = await user_for(session, p)
            await phone_for(session, request, user)
            await set_block(session, blocker_id=user.id, blocked_id=str(user_id), blocked=body.blocked, now=now())
            return {"blocked": body.blocked}

    from .groups_api import install as install_groups
    install_groups(app, settings, db, now, principal, user_for, phone_for, rate)
    return app


def application():
    return create_app(Settings())
