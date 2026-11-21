"""Opaque immutable attachment storage and exact-device message grants.

Keys, filenames, MIME types, dimensions and thumbnails are inside Signal, not
these records. The filesystem backend is the isolated vertical-slice store.
"""
import asyncio
from datetime import timedelta
import hashlib
import os
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, delete, func, or_, select
from starlette.responses import JSONResponse, StreamingResponse

from .db import Block, Device, MediaBlob, MediaCleanup, MediaGrant, PendingMessage, User
from .delivery import DeliveryError, utc


class MediaTransferLimits:
    """Bound both socket lifetime and worker file descriptors, including a
    blocked ASGI send. A generator-only timer cannot bound a stalled reader.
    """
    def __init__(self, app, *, seconds, connections):
        self.app, self.seconds, self.connections = app, seconds, connections
        self.active = 0

    async def __call__(self, scope, receive, send):
        parts = scope.get('path', '').split('/')
        media = scope['type'] == 'http' and scope.get('method') in {'GET', 'HEAD', 'PUT'} and (
            len(parts) == 5 and parts[1:3] == ['v1', 'media'] and parts[4] == 'ciphertext')
        # Bound the complete route shape. FastAPI accepts upper-case, compact
        # and braced UUIDs too; normalizing only canonical text permits bypass.
        if not media:
            return await self.app(scope, receive, send)
        if self.active >= self.connections:
            return await JSONResponse({'error': 'media_busy'}, status_code=429,
                headers={'Retry-After': '1'})(scope, receive, send)
        self.active += 1
        started = False
        async def tracked(event):
            nonlocal started
            if event['type'] == 'http.response.start':
                started = True
            await send(event)
        try:
            try:
                async with asyncio.timeout(self.seconds):
                    await self.app(scope, receive, tracked)
            except TimeoutError:
                if started:
                    # A partial200 must terminate; never manufacture a complete
                    # ciphertext body. Native size/hash/GCM checks reject it.
                    raise
                await JSONResponse({'error': 'media_transfer_timeout'}, status_code=408)(scope, receive, send)
        finally:
            self.active -= 1


class CiphertextResponse(StreamingResponse):
    """Own the descriptor even if cancellation precedes the first body chunk."""
    def __init__(self, stream, *, headers):
        self.stream = stream
        async def chunks():
            while chunk := stream.read(65536):
                yield chunk
        super().__init__(chunks(), media_type='application/octet-stream', headers=headers)

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.stream.close()


class MediaCapabilityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(strict=True, ge=1, le=1)


class UploadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    ciphertext_bytes: int = Field(ge=32)
    ciphertext_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def metadata(blob):
    return {"id": blob.id, "state": blob.state, "ciphertext_bytes": blob.ciphertext_bytes,
            "ciphertext_sha256": blob.ciphertext_sha256, "expires_at": utc(blob.expires_at).isoformat()}


class CiphertextStore:
    def __init__(self, root):
        self.root = Path(root)
        if not self.root.is_absolute() or self.root.is_symlink():
            raise ValueError("Media storage needs an explicit owned absolute directory")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def path(self, ident):
        assert str(UUID(ident)) == ident
        return self.root / (ident + ".ciphertext")

    def temporary(self, ident, token):
        self.path(ident)
        assert str(UUID(token)) == token
        return self.root / (ident + "." + token + ".part")

    def remove(self, ident):
        self.path(ident).unlink(missing_ok=True)
        for part in self.root.glob(ident + ".*.part"):
            part.unlink(missing_ok=True)
        descriptor = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


    def finalized_matches(self, ident, expected_size, expected_hash):
        """Verify opaque finalized bytes without ever loading the whole file."""
        path = self.path(ident)
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return False
        digest = hashlib.sha256()
        count = 0
        with os.fdopen(descriptor, 'rb') as source:
            if os.fstat(source.fileno()).st_size != expected_size:
                return False
            while chunk := source.read(65536):
                count += len(chunk)
                if count > expected_size:
                    return False
                digest.update(chunk)
        return count == expected_size and digest.hexdigest() == expected_hash


async def recover_finalized(blob, store):
    """Caller holds the blob row lock, serializing finalize/cancel/recovery.

    A worker can die after atomic filesystem finalize but before its SQL commit.
    The immutable expected digest/size let the exact owner reconcile that result;
    no key, plaintext or changed authorization is involved.
    """
    if blob.state != 'uploading':
        return False
    complete = await asyncio.to_thread(store.finalized_matches, blob.id,
                                      blob.ciphertext_bytes, blob.ciphertext_sha256)
    if complete:
        blob.state, blob.upload_token, blob.lease_until = 'ready', None, None
    return complete


async def owner_blob(session, ident, user_id, device_id, now, *, lock=False):
    query = select(MediaBlob).where(MediaBlob.id == ident, MediaBlob.owner_id == user_id,
        MediaBlob.owner_device_id == device_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    blob = await session.scalar(query)
    if blob is None or utc(blob.expires_at) <= utc(now) or blob.state in {"cancelled", "expired"}:
        raise DeliveryError("media_unavailable", 404)
    return blob


async def grant_attachments(session, envelope, now):
    """Called inside the SAME delivery transaction, after its user/device locks."""
    for ident in sorted(envelope.attachment_ids):
        blob = await owner_blob(session, ident, envelope.sender_id, envelope.sender_device_id, now, lock=True)
        if blob.state != "ready":
            raise DeliveryError("media_not_ready", 409)
        # Blob availability must cover the complete admitted envelope lifetime,
        # including an offline draft sent late in the reservation window.
        grant_expires = utc(envelope.created_at) + timedelta(hours=72)
        blob.expires_at = max(utc(blob.expires_at), grant_expires)
        grant = await session.get(MediaGrant, (ident, envelope.id))
        if grant is None:
            session.add(MediaGrant(blob_id=ident, message_id=envelope.id, recipient_id=envelope.recipient_id,
                recipient_device_id=envelope.recipient_device_id, expires_at=grant_expires))
        elif (grant.recipient_id, grant.recipient_device_id) != (envelope.recipient_id, envelope.recipient_device_id):
            raise DeliveryError("message_id_conflict", 409)


async def enqueue_cleanup(session, ident, now):
    # Caller holds the blob lock (or account lifecycle lock before removing it).
    if await session.get(MediaCleanup, ident) is None:
        session.add(MediaCleanup(blob_id=ident, created_at=utc(now)))


async def cancel_owned_blob(session, ident, user_id, device_id, now):
    """Blob lock orders cancellation against transactional message grants."""
    blob = await session.scalar(select(MediaBlob).where(
        MediaBlob.id == ident, MediaBlob.owner_id == user_id,
        MediaBlob.owner_device_id == device_id).with_for_update())
    if blob is None:
        return False
    if await session.scalar(select(MediaGrant).where(MediaGrant.blob_id == ident).limit(1)):
        raise DeliveryError('media_already_sent', 409)
    blob.state, blob.upload_token, blob.lease_until = 'cancelled', None, None
    await enqueue_cleanup(session, ident, now)
    return True


async def download_blob(session, ident, user_id, device_id, now):
    blob = await session.get(MediaBlob, ident)
    if blob is None or blob.state != "ready" or utc(blob.expires_at) <= utc(now):
        raise DeliveryError("media_unavailable", 404)
    owner = await session.get(User, blob.owner_id)
    if owner is None or owner.deleted or owner.suspended:
        raise DeliveryError("media_unavailable", 404)
    if (blob.owner_id,blob.owner_device_id) == (user_id,device_id):
        return blob
    granted = await session.scalar(select(MediaGrant).where(MediaGrant.blob_id==ident,
        MediaGrant.recipient_id==user_id,MediaGrant.recipient_device_id==device_id,MediaGrant.expires_at>now).limit(1))
    blocked = await session.scalar(select(Block).where(or_(
        and_(Block.blocker_id==user_id,Block.blocked_id==blob.owner_id),
        and_(Block.blocker_id==blob.owner_id,Block.blocked_id==user_id))))
    if granted is None or blocked is not None:
        raise DeliveryError("media_unavailable", 404)
    return blob


async def erase_account_media(session, account_id, now):
    """Commit revocation and durable cleanup before account/message erasure."""
    rows = (await session.scalars(select(MediaBlob).where(
        MediaBlob.owner_id == account_id).order_by(MediaBlob.id).with_for_update())).all()
    for blob in rows:
        await enqueue_cleanup(session, blob.id, now)
    # Explicit order also works with SQLite foreign-key checking enabled.
    await session.execute(delete(MediaGrant).where(or_(
        MediaGrant.recipient_id == account_id,
        MediaGrant.blob_id.in_([blob.id for blob in rows]))))
    for blob in rows:
        await session.delete(blob)
    await session.flush()


async def expire_media(session, store, now, limit=100):
    rows = (await session.scalars(select(MediaBlob).where(MediaBlob.expires_at<=now,
        MediaBlob.state.not_in(["expired","cancelled"])).order_by(MediaBlob.expires_at).limit(limit).with_for_update())).all()
    for blob in rows:
        blob.state,blob.upload_token,blob.lease_until="expired",None,None
        await enqueue_cleanup(session, blob.id, now)
    # Tombstones outlive the message retry ledger. Never retire a pending removal.
    await session.execute(delete(MediaBlob).where(
        MediaBlob.expires_at < utc(now) - timedelta(days=7),
        MediaBlob.state.in_(['expired', 'cancelled']),
        ~MediaBlob.id.in_(select(MediaCleanup.blob_id))))
    return len(rows)


async def drain_cleanup(db, store, limit=100, *, ident=None):
    """Retry-safe removal: only committed intents; failures retain the intent.

    Hold its row lock through fsync. A crash before SQL commit repeats unlink;
    a crash before the deletion transaction commits never reaches this worker.
    """
    removed = 0
    async with db.sessions.begin() as session:
        query = select(MediaCleanup).order_by(MediaCleanup.created_at).limit(limit)
        if ident is not None:
            query = query.where(MediaCleanup.blob_id == ident)
        rows = (await session.scalars(query.with_for_update(skip_locked=True))).all()
        for row in rows:
            await asyncio.to_thread(store.remove, row.blob_id)
            await session.delete(row)
            removed += 1
    return removed


def install(app, settings, db, principal, user_for, phone_for, rate, now):
    store = CiphertextStore(settings.media_storage_path) if settings.media_enabled else None
    if store is not None:
        app.add_middleware(MediaTransferLimits, seconds=settings.media_transfer_timeout_seconds,
                           connections=settings.media_transfers_per_worker)
    def enabled():
        if store is None:
            raise DeliveryError("media_unavailable", 404)

    async def identity(session, request, p):
        user=await user_for(session,p)
        device=await phone_for(session,request,user)
        return user,device

    # Dependencies use the existing verified bearer/device path unchanged.
    from typing import Annotated
    from fastapi import Depends
    from .auth import Principal

    @app.put("/v1/media/capability")
    async def register_capability(body: MediaCapabilityInput, request: Request, p: Annotated[Principal, Depends(principal)]):
        enabled()
        await rate(p, "media-capability-register", 60)
        async with db.sessions.begin() as session:
            _, device = await identity(session, request, p)
            device.media_version = body.version
        return {"version": body.version}

    @app.get("/v1/media/capability/{peer_id}")
    async def peer_capability(peer_id: UUID, request: Request, p: Annotated[Principal, Depends(principal)]):
        enabled()
        await rate(p, "media-capability-read", 120)
        async with db.sessions() as session:
            user, _ = await identity(session, request, p)
            peer = await session.get(User, str(peer_id))
            if not peer or peer.deleted or peer.suspended:
                raise DeliveryError("recipient_unavailable", 404)
            blocked = await session.scalar(select(Block).where(or_(
                and_(Block.blocker_id == user.id, Block.blocked_id == peer.id),
                and_(Block.blocker_id == peer.id, Block.blocked_id == user.id),
            )))
            if blocked:
                raise DeliveryError("recipient_unavailable", 404)
            device = await session.scalar(select(Device).where(Device.user_id == peer.id, Device.active.is_(True)))
            return {"version": device.media_version if device and not settings.media_draining else 0, "device_id": device.id if device else None}

    @app.post('/v1/media/uploads')
    async def create_upload(body: UploadInput,request: Request,p: Annotated[Principal,Depends(principal)]):
        enabled();await rate(p,'media-create',30)
        if body.ciphertext_bytes>settings.media_max_bytes:
            raise DeliveryError('media_too_large',413)
        async with db.sessions.begin() as session:
            user,device=await identity(session,request,p)
            await session.execute(select(User).where(User.id==user.id).with_for_update())
            existing=await session.get(MediaBlob,str(body.id))
            if await session.get(MediaCleanup, str(body.id)) is not None:
                raise DeliveryError('media_unavailable', 404)
            if existing:
                if (existing.owner_id,existing.owner_device_id)!=(user.id,device.id):
                    raise DeliveryError('media_unavailable',404)
                if (existing.ciphertext_bytes,existing.ciphertext_sha256)!=(body.ciphertext_bytes,body.ciphertext_sha256):
                    raise DeliveryError('media_id_conflict',409)
                if existing.state in {'cancelled','expired'} or utc(existing.expires_at)<=now():
                    raise DeliveryError('media_unavailable',404)
                return metadata(existing)
            if settings.media_draining:
                raise DeliveryError("media_draining", 503)
            used=await session.scalar(select(func.coalesce(func.sum(MediaBlob.ciphertext_bytes),0)).where(
                MediaBlob.owner_id==user.id,MediaBlob.expires_at>now(),MediaBlob.state.in_(['uploading','ready'])))
            count=await session.scalar(select(func.count()).select_from(MediaBlob).where(
                MediaBlob.owner_id==user.id,MediaBlob.expires_at>now(),MediaBlob.state.in_(['uploading','ready'])))
            if count>=32 or used+body.ciphertext_bytes>settings.media_owner_bytes:
                raise DeliveryError('media_storage_full',429)
            blob=MediaBlob(id=str(body.id),owner_id=user.id,owner_device_id=device.id,
                ciphertext_bytes=body.ciphertext_bytes,ciphertext_sha256=body.ciphertext_sha256,
                created_at=now(),expires_at=now()+timedelta(hours=72),state='uploading')
            session.add(blob);await session.flush();return metadata(blob)

    @app.get('/v1/media/uploads/{ident}')
    async def upload_status(ident: UUID,request: Request,p: Annotated[Principal,Depends(principal)]):
        enabled();await rate(p,'media-status',120)
        async with db.sessions.begin() as session:
            user, device = await identity(session, request, p)
            blob = await owner_blob(session, str(ident), user.id, device.id, now(), lock=True)
            await recover_finalized(blob, store)
            return metadata(blob)

    @app.put('/v1/media/{ident}/ciphertext')
    async def upload(ident: UUID,request: Request,p: Annotated[Principal,Depends(principal)]):
        enabled();await rate(p,'media-upload',30);ident=str(ident);token=str(uuid4())
        async with db.sessions.begin() as session:
            user,device=await identity(session,request,p)
            blob=await owner_blob(session,ident,user.id,device.id,now(),lock=True)
            await recover_finalized(blob, store)
            if blob.state=='ready':return metadata(blob)
            if blob.upload_token and blob.lease_until and utc(blob.lease_until)>now():
                raise DeliveryError('media_upload_in_progress',409)
            blob.upload_token,blob.lease_until=token,now()+timedelta(minutes=15)
            expected_size,expected_hash=blob.ciphertext_bytes,blob.ciphertext_sha256
        temporary=store.temporary(ident,token);digest=hashlib.sha256();size=0
        try:
            with temporary.open('xb') as target:
                os.chmod(temporary,0o600)
                try:
                    async with asyncio.timeout(settings.media_upload_timeout_seconds):
                        async for chunk in request.stream():
                            size += len(chunk)
                            if size > expected_size:
                                raise DeliveryError('media_upload_invalid', 413)
                            digest.update(chunk)
                            target.write(chunk)
                except TimeoutError:
                    raise DeliveryError('media_upload_timeout', 408) from None
                target.flush();os.fsync(target.fileno())
            if size!=expected_size or digest.hexdigest()!=expected_hash:
                raise DeliveryError('media_upload_incomplete',409)
            async with db.sessions.begin() as session:
                user,device=await identity(session,request,p)
                blob=await owner_blob(session,ident,user.id,device.id,now(),lock=True)
                if blob.upload_token!=token:raise DeliveryError('media_upload_cancelled',409)
                os.replace(temporary,store.path(ident))
                directory=os.open(store.root,os.O_RDONLY)
                try:os.fsync(directory)
                finally:os.close(directory)
                blob.state,blob.upload_token,blob.lease_until='ready',None,None
                result=metadata(blob)
            return result
        finally:
            temporary.unlink(missing_ok=True)
            async def release():
                async with db.sessions.begin() as session:
                    blob=await session.get(MediaBlob,ident,with_for_update=True)
                    if blob and blob.upload_token==token:
                        blob.upload_token,blob.lease_until=None,None
            await asyncio.shield(release())

    @app.delete('/v1/media/uploads/{ident}')
    async def cancel(ident: UUID,request: Request,p: Annotated[Principal,Depends(principal)]):
        enabled();ident=str(ident);await rate(p,'media-cancel',60)
        async with db.sessions.begin() as session:
            user,device=await identity(session,request,p)
            # Idempotent cancellation reveals no foreign/missing object state.
            owned = await cancel_owned_blob(session, ident, user.id, device.id, now())
        if owned:
            await drain_cleanup(db, store, ident=ident)
        return {'cancelled':True}

    @app.get('/v1/media/{ident}/ciphertext')
    async def download(ident: UUID,request: Request,p: Annotated[Principal,Depends(principal)]):
        enabled();ident=str(ident);await rate(p,'media-download',120)
        async with db.sessions() as session:
            user,device=await identity(session,request,p)
            blob=await download_blob(session,ident,user.id,device.id,now())
            expected_size,expected_hash=blob.ciphertext_bytes,blob.ciphertext_sha256
        path=store.path(ident)
        try:stream=path.open('rb')
        except FileNotFoundError:raise DeliveryError('media_unavailable',404) from None
        return CiphertextResponse(stream,headers={
            'Content-Length':str(expected_size),'X-Ciphertext-SHA256':expected_hash,'Cache-Control':'no-store'})
