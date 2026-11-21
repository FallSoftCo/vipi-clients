"""Opaque immutable attachment storage and exact-device message grants.

Keys, filenames, MIME types, dimensions and thumbnails are inside Signal, not
these records. The filesystem backend is the isolated vertical-slice store.
"""
import asyncio
from datetime import timedelta
import errno
import fcntl
import hashlib
import os
from contextlib import ExitStack, contextmanager
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, case, delete, func, or_, select, text, true
from starlette.responses import JSONResponse, StreamingResponse

from .config import MAX_CIPHERTEXT_BYTES
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
    def __init__(self, root, *, volume_id=None, require_existing=False):
        self.root = Path(root)
        self.volume_id = str(volume_id) if volume_id is not None else None
        self.identity = None
        if not self.root.is_absolute() or self.root.is_symlink():
            raise ValueError("Media storage needs an explicit owned absolute directory")
        if require_existing and (not self.root.is_dir() or not self.volume_id):
            raise ValueError("The provisioned media directory and volume ID are required")
        if not require_existing:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self.directory() as directory:
            st = os.fstat(directory)
            self.identity = st.st_dev, st.st_ino

    @classmethod
    def configured(cls, settings):
        return cls(settings.media_storage_path, volume_id=settings.media_volume_id,
                   require_existing=settings.environment in {"staging", "production"})

    @contextmanager
    def directory(self):
        try:
            fd = os.open(self.root, os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as exc:
            raise DeliveryError("media_storage_unavailable", 507) from exc
        try:
            st = os.fstat(fd)
            if self.identity is not None and (st.st_dev, st.st_ino) != self.identity:
                raise DeliveryError("media_storage_unavailable", 507)
            if self.volume_id is not None:
                try:
                    marker = os.open(".vipi-volume-id", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                    try:
                        value = os.read(marker, 64)
                    finally:
                        os.close(marker)
                except OSError as exc:
                    raise DeliveryError("media_storage_unavailable", 507) from exc
                if value not in (self.volume_id.encode(), (self.volume_id + "\n").encode()):
                    raise DeliveryError("media_storage_unavailable", 507)
            yield fd
        finally:
            os.close(fd)

    def path(self, ident):
        assert str(UUID(ident)) == ident
        return self.root / (ident + ".ciphertext")

    def temporary(self, ident, token):
        self.path(ident)
        assert str(UUID(token)) == token
        return self.root / (ident + "." + token + ".part")

    def remove(self, ident):
        # An unlinked but open inode still consumes disk. Keep its SQL cleanup
        # intent charged while a download or an interrupted PUT owns the file.
        final_name = self.path(ident).name
        with self.directory() as directory:
            names = [final_name]
            with os.scandir(directory) as entries:
                names.extend(e.name for e in entries if e.name.startswith(ident + ".") and e.name.endswith(".part"))
            for name in names:
                try:
                    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
                except FileNotFoundError:
                    continue
                with os.fdopen(fd, "rb") as stream:
                    try:
                        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        return False
                    try:
                        os.unlink(name, dir_fd=directory)
                    except FileNotFoundError:
                        pass
            os.fsync(directory)
        return True

    def finalized_matches(self, ident, expected_size, expected_hash):
        """Verify opaque finalized bytes without ever loading the whole file."""
        path = self.path(ident)
        try:
            with self.directory() as directory:
                descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
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


async def storage_operation(function, *args):
    """Finish an outstanding filesystem operation before relinquishing its DB lock."""
    work = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        while not work.done():
            try:
                await asyncio.shield(work)
            except asyncio.CancelledError:
                continue
        if not work.cancelled():
            work.exception()
        raise


async def lock_capacity(session):
    # All API workers use the same transaction-scoped PostgreSQL lock.
    # SQLite has one writer; taking it before reading avoids a stale snapshot.
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(1447645257, 1)"))
    else:
        await session.execute(text("UPDATE media_blobs SET id=id WHERE 0=1"))


async def check_capacity(session, store, settings, *, new_bytes=None):
    # One SQL snapshot. Revoked rows count until the cleanup worker has
    # unlinked AND fsynced the directory. Account deletion removes the owner
    # row and its original length, leaving an independent cleanup intent.
    # Charge the historical per-object ceiling for each size-unknown intent.
    live = MediaBlob.state.in_(["uploading", "ready"])
    uploading = MediaBlob.state == "uploading"
    reservations = select(
        func.coalesce(func.sum(MediaBlob.ciphertext_bytes), 0).label("used"),
        func.count().label("blobs"),
        func.coalesce(func.sum(case((uploading, MediaBlob.ciphertext_bytes), else_=0)), 0).label("pending"),
        func.count(case((uploading, 1))).label("pending_count"),
    ).where(live).subquery()
    revoked = select(
        func.coalesce(func.sum(func.coalesce(MediaBlob.ciphertext_bytes, MAX_CIPHERTEXT_BYTES)), 0).label("used"),
        func.count().label("blobs"),
    ).select_from(MediaCleanup).outerjoin(MediaBlob, MediaBlob.id == MediaCleanup.blob_id
    ).where(or_(MediaBlob.id.is_(None), ~live)).subquery()
    totals = select(reservations.c.used + revoked.c.used, reservations.c.blobs + revoked.c.blobs,
                    reservations.c.pending, reservations.c.pending_count).select_from(reservations.join(revoked, true()))
    used, count, outstanding, outstanding_count = (await session.execute(totals)).one()
    added = int(new_bytes is not None)
    requested = new_bytes or 0
    if used + requested > settings.media_global_bytes or count + added > settings.media_global_blobs:
        raise DeliveryError("media_storage_full", 429)

    with store.directory() as directory:
        space = os.fstatvfs(directory)
    # Charge full unwritten declarations, even when another PUT has already
    # allocated part of its file. Round conservatively for filesystem blocks.
    outstanding_count += added
    headroom = space.f_bavail * space.f_frsize - settings.media_min_free_bytes
    required = outstanding + requested + outstanding_count * (space.f_frsize - 1)
    if headroom < required or space.f_favail - outstanding_count < settings.media_min_free_inodes:
        raise DeliveryError("media_storage_unavailable", 507)


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
    blob = await session.get(MediaBlob, ident, with_for_update={"read": True})
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
            if not await storage_operation(store.remove, row.blob_id):
                continue
            await session.delete(row)
            removed += 1
    return removed


def install(app, settings, db, principal, user_for, phone_for, rate, now):
    store = CiphertextStore.configured(settings) if settings.media_enabled else None
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
            await lock_capacity(session)
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
            await check_capacity(session, store, settings, new_bytes=body.ciphertext_bytes)
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
        temporary = store.temporary(ident, token)
        target = None
        with ExitStack() as files:
            try:
                async with db.sessions.begin() as session:
                    user, device = await identity(session, request, p)
                    await lock_capacity(session)
                    blob = await owner_blob(session, ident, user.id, device.id, now(), lock=True)
                    if await recover_finalized(blob, store) or blob.state == "ready":
                        return metadata(blob)
                    if blob.upload_token and blob.lease_until and utc(blob.lease_until) > now():
                        raise DeliveryError("media_upload_in_progress", 409)
                    expected_size, expected_hash = blob.ciphertext_bytes, blob.ciphertext_sha256
                    if not await storage_operation(store.remove, ident):
                        raise DeliveryError("media_upload_in_progress", 409)
                    await check_capacity(session, store, settings)
                    directory = files.enter_context(store.directory())
                    fd = os.open(temporary.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory)
                    def discard_partial():
                        try:
                            os.unlink(temporary.name, dir_fd=directory)
                        except FileNotFoundError:
                            pass
                    files.callback(discard_partial)
                    target = files.enter_context(os.fdopen(fd, "wb"))
                    fcntl.flock(target, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    # Finish the kernel reservation before releasing its file or
                    # DB lock, including when the HTTP request is cancelled.
                    allocate = getattr(os, "posix_fallocate", None)
                    if allocate is None:
                        raise DeliveryError("media_storage_unavailable", 507)
                    await storage_operation(allocate, fd, 0, expected_size)
                    blob.upload_token, blob.lease_until = token, now() + timedelta(minutes=15)

                digest = hashlib.sha256()
                size = 0
                try:
                    async with asyncio.timeout(settings.media_upload_timeout_seconds):
                        async for chunk in request.stream():
                            size += len(chunk)
                            if size > expected_size:
                                raise DeliveryError("media_upload_invalid", 413)
                            digest.update(chunk)
                            target.write(chunk)
                except TimeoutError:
                    raise DeliveryError("media_upload_timeout", 408) from None
                if size != expected_size or digest.hexdigest() != expected_hash:
                    raise DeliveryError("media_upload_incomplete", 409)
                target.flush()
                os.fsync(target.fileno())
                async with db.sessions.begin() as session:
                    user, device = await identity(session, request, p)
                    blob = await owner_blob(session, ident, user.id, device.id, now(), lock=True)
                    if blob.upload_token != token:
                        raise DeliveryError("media_upload_cancelled", 409)
                    os.replace(temporary.name, store.path(ident).name, src_dir_fd=directory, dst_dir_fd=directory)
                    os.fsync(directory)
                    files.close()
                    blob.state, blob.upload_token, blob.lease_until = "ready", None, None
                    return metadata(blob)
            except OSError as exc:
                if exc.errno in (errno.ENOSPC, errno.EDQUOT, errno.EOPNOTSUPP, errno.ENOSYS):
                    raise DeliveryError("media_storage_unavailable", 507) from None
                raise
            finally:
                # Close the descriptor before unlink so no invisible allocated
                # storage outlives the cleanup intent. Release only our token.
                files.close()
                if target is not None:
                    async def release():
                        async with db.sessions.begin() as session:
                            blob = await session.get(MediaBlob, ident, with_for_update=True)
                            if blob and blob.upload_token == token:
                                blob.upload_token, blob.lease_until = None, None
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
            try:
                with store.directory() as directory:
                    fd = os.open(store.path(ident).name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
                stream = os.fdopen(fd, 'rb')
            except FileNotFoundError:
                raise DeliveryError('media_unavailable',404) from None
            try:
                fcntl.flock(stream, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BaseException:
                stream.close()
                raise
        return CiphertextResponse(stream,headers={
            'Content-Length':str(expected_size),'X-Ciphertext-SHA256':expected_hash,'Cache-Control':'no-store'})
