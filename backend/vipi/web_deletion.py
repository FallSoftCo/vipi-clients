"""Same-origin account deletion, with fresh AuthKit sign-in and no browser JS.

Short-lived credentials stay in authenticated, encrypted HttpOnly cookies.
A separate seven-day receipt survives sign-in removal and lost POST responses.
Only the explicitly configured HTTPS origin can issue state-changing requests.
"""
import base64
import hashlib
import hmac
from html import escape
import json
from pathlib import Path
import secrets
from urllib.parse import parse_qs, urlencode
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Request
import httpx
from sqlalchemy import select
from starlette.responses import HTMLResponse, RedirectResponse, Response

from .auth import AuthenticationError
from .db import AccountDeletion, User
from .deletion import deletion_for, request_deletion, subject_hash, lock_account_lifecycle
from .delivery import DeliveryError
from .rates import consume

START = "__Host-vipi-delete-start"
AUTH = "__Host-vipi-delete-auth"
RECEIPT = "__Host-vipi-delete-receipt"
SHORT = 600
WEEK = 7 * 86400


def install(app, settings, db, verifier, clock, *, provider_transport=None):
    origin = settings.deletion_web_origin
    # Domain separation; changing the service secret invalidates these cookies.
    key = hmac.new(settings.service_secret.encode(), b"vipi-browser-deletion-cookie-v1", hashlib.sha256).digest()
    box = Fernet(base64.urlsafe_b64encode(key))

    def timestamp():
        return int(clock().timestamp())

    def read(request, name, ttl):
        try:
            raw = request.cookies.get(name, "")
            if not raw or len(raw) > 3800:
                return None
            value = json.loads(box.decrypt_at_time(raw.encode(), ttl, timestamp()))
            return value if value.get("kind") == name else None
        except (InvalidToken, ValueError, TypeError, UnicodeError):
            return None

    def write(response, name, value, age):
        raw = box.encrypt_at_time(json.dumps(value | {"kind": name}, separators=(",", ":")).encode(), timestamp()).decode()
        if len(raw) > 3800:
            raise DeliveryError("browser_session_unavailable", 503)
        response.set_cookie(name, raw, max_age=age, secure=True, httponly=True, samesite="lax", path="/")

    def clear(response, *names):
        for name in names:
            response.delete_cookie(name, secure=True, httponly=True, samesite="lax", path="/")
        return response

    def headers(response):
        response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "same-origin",
            "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'none'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()"})
        return response

    def page(title, body, status=200):
        return headers(HTMLResponse('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark">'
            f'<title>{escape(title)} · Vipi</title><link rel="stylesheet" href="/delete-account/style.css"></head>'
            '<body><main><a class="brand" href="/delete-account" aria-label="Vipi account deletion">vipi<span>●</span></a>'
            f'<h1>{escape(title)}</h1>{body}</main><footer>Vipi · Fallible Software, Co.</footer></body></html>', status_code=status))

    def form(action, csrf, label, *, danger=False):
        return (f'<form method="post" action="/delete-account/{action}"><input type="hidden" name="csrf" value="{escape(csrf, quote=True)}">'
            f'<button class="{"danger" if danger else "primary"}" type="submit">{escape(label)}</button></form>')

    subscription = ('<details><summary>Subscriptions and copies of messages</summary><p>Deleting your account does not cancel a store subscription. '
        'You can cancel it in <a href="https://apps.apple.com/account/subscriptions" rel="noreferrer">Apple subscriptions</a> or '
        '<a href="https://play.google.com/store/account/subscriptions" rel="noreferrer">Google Play subscriptions</a>. '
        'You do not need to cancel first.</p><p>Friends’ copies of messages and backups you saved outside Vipi remain. '
        'This website cannot erase chat history stored on your devices. Remove that history in the app or remove the app’s local data.</p></details>')

    async def throttle(request, scope, limit):
        remote = request.client.host if request.client else "unknown"
        async with db.sessions.begin() as session:
            await consume(session, subject="web-delete:"+subject_hash(remote, settings.service_secret), scope=scope,
                          now=clock().timestamp(), limit=limit)

    async def posted(request, session):
        if request.headers.get("origin") != origin or request.headers.get("content-type", "").split(";", 1)[0] != "application/x-www-form-urlencoded":
            raise DeliveryError("browser_request_unavailable", 403)
        try:
            data = parse_qs((await request.body()).decode("utf-8"), strict_parsing=True, max_num_fields=2)
            csrf = data.get("csrf", [])
            valid = session and set(data) == {"csrf"} and len(csrf) == 1 and hmac.compare_digest(csrf[0], session["csrf"])
        except (ValueError, UnicodeError, KeyError):
            valid = False
        if not valid:
            raise DeliveryError("browser_request_unavailable", 403)

    async def identity(auth):
        if not auth:
            raise AuthenticationError("sign_in_required")
        p = await verifier.verify(auth["token"])
        if p.subject != auth["subject"] or (settings.allowed_subjects and p.subject not in settings.allowed_subjects):
            raise AuthenticationError("sign_in_required")
        if not 0 <= timestamp() - p.authenticated_at <= SHORT:
            raise AuthenticationError("sign_in_required")
        return p

    async def job_for(receipt):
        if not receipt:
            return None
        async with db.sessions() as session:
            # This sealed cookie proves the authenticated subject independently
            # of a native client's receipt or an unfinished profile's UUID.
            job = await session.scalar(select(AccountDeletion).where(AccountDeletion.subject_hash == receipt["subject_hash"]))
            if job and hmac.compare_digest(job.subject_hash, receipt["subject_hash"]):
                return job
        return None

    def progress(job):
        if job.finished_at:
            response = page("Account deleted", '<p class="lead">Your Vipi account and sign-in have been deleted.</p>'
                '<p>You can close this page.</p>'+subscription+
                '<p class="small">A minimal deletion receipt is retained for seven days to let you check completion.</p>')
        else:
            response = page("Deletion in progress", '<p class="lead">Your Vipi account data has been removed. We’re finishing the removal of your sign-in.</p>'
                '<p>You can close this page. Deletion continues automatically. Return in this browser within seven days to check completion.</p>'
                '<a class="button" href="/delete-account">Check status</a>'+subscription)
        return clear(response, AUTH, START)

    def unavailable(message, status=400):
        return page("We couldn’t continue", f'<p class="lead">{escape(message)}</p><a class="button" href="/delete-account">Return to account deletion</a>', status)

    @app.middleware("http")
    async def protect_web(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/delete-account"):
            if response.status_code >= 400 and response.headers.get("content-type", "").startswith("application/json"):
                message = "Please wait a minute before trying again." if response.status_code == 429 else "This request could not be verified. Please return and sign in again."
                replacement = unavailable(message, response.status_code)
                if response.status_code == 429:
                    replacement.headers["Retry-After"] = "60"
                return replacement
            return headers(response)
        return response

    @app.get("/delete-account/style.css")
    async def stylesheet():
        return headers(Response(Path(__file__).with_name("deletion.css").read_text(), media_type="text/css"))

    @app.get("/delete-account")
    async def landing(request: Request):
        if not origin:
            return page("Delete your Vipi account", '<p class="lead">Browser account deletion is not available yet.</p><p>Please use Delete account in the app’s settings.</p>', 503)
        await throttle(request, "web-deletion-read", 120)
        receipt = read(request, RECEIPT, WEEK)
        if job := await job_for(receipt):
            return progress(job)
        auth = read(request, AUTH, SHORT)
        if auth and receipt and auth.get("account") == receipt.get("account"):
            try:
                await identity(auth)
            except AuthenticationError:
                auth = None
            if auth:
                return page("Delete your account?", f'<p class="identity">{escape(auth["label"])}</p>'
                    '<p class="lead">Permanently delete your Vipi profile, sign-in, device registrations and messages waiting for delivery.</p>'
                    '<p>This cannot be undone. Store subscriptions must be canceled separately.</p>'+subscription+
                    '<div class="actions">'+form("confirm", auth["csrf"], "Delete account", danger=True)+form("cancel", auth["csrf"], "Cancel")+'</div>')
        response = page("Delete your Vipi account", '<p class="lead">Sign in to confirm which account you want to delete. You’ll review the details before anything is deleted.</p>'
            +'<a class="button" href="/delete-account/sign-in">Sign in to continue</a>'+subscription)
        return clear(response, AUTH)

    @app.get("/delete-account/sign-in")
    async def sign_in(request: Request):
        if not origin:
            return unavailable("Browser deletion is not available yet.", 503)
        await throttle(request, "web-deletion-sign-in", 10)
        if job := await job_for(read(request, RECEIPT, WEEK)):
            return progress(job)
        pending = {"csrf": secrets.token_urlsafe(32), "state": secrets.token_urlsafe(32), "verifier": secrets.token_urlsafe(48)}
        challenge = base64.urlsafe_b64encode(hashlib.sha256(pending["verifier"].encode()).digest()).rstrip(b"=").decode()
        params = {"client_id": settings.workos_client_id, "provider": "authkit", "response_type": "code", "max_age": "0", "screen_hint": "sign-in",
            "redirect_uri": origin+"/delete-account/callback", "state": pending["state"], "code_challenge_method": "S256", "code_challenge": challenge}
        response = headers(RedirectResponse("https://api.workos.com/user_management/authorize?"+urlencode(params), status_code=303))
        write(response, START, pending, SHORT)
        return clear(response, AUTH)

    @app.get("/delete-account/callback")
    async def callback(request: Request):
        await throttle(request, "web-deletion-callback", 20)
        pending = read(request, START, SHORT)
        params = request.query_params
        if not origin or not pending or not pending.get("state") or len(params.getlist("state")) != 1 or not hmac.compare_digest(params["state"], pending["state"]):
            return unavailable("This sign-in could not be verified. Please start again.")
        if len(params.getlist("code")) != 1 or not 1 <= len(params["code"]) <= 2048 or params.get("error"):
            return clear(unavailable("Sign-in did not finish. Nothing has been deleted."), START)
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False, transport=provider_transport) as http:
                upstream = await http.post("https://api.workos.com/user_management/authenticate", json={
                    "client_id": settings.workos_client_id, "client_secret": settings.workos_api_key.get_secret_value(),
                    "grant_type": "authorization_code", "code": params["code"], "code_verifier": pending["verifier"]})
                upstream.raise_for_status()
                result = upstream.json()
            auth = {"token": result["access_token"], "subject": result["user"]["id"], "csrf": secrets.token_urlsafe(32)}
            p = await identity(auth)
            old = read(request, RECEIPT, WEEK)
            digest = subject_hash(p.subject, settings.service_secret)
            async with db.sessions() as session:
                job = await deletion_for(session, p.subject, settings.service_secret)
                user = await session.scalar(select(User).where(User.subject == p.subject))
                previous_account = old["account"] if old and old.get("subject_hash") == digest else str(uuid4())
                account = job.account_id if job else (user.id if user else previous_account)
                auth["label"] = "@"+user.username if user else result["user"]["email"]
            auth["account"] = account
            receipt = old if old and old.get("account") == account and old.get("subject_hash") == digest else {
                "account": account, "subject_hash": digest, "secret": secrets.token_urlsafe(32)}
            response = headers(RedirectResponse("/delete-account", status_code=303))
            # Receipt reaches the browser before it can confirm the destructive
            # action; it also grants status for an existing native deletion job.
            write(response, RECEIPT, receipt, WEEK)
            if not job:
                write(response, AUTH, auth, SHORT)
            else:
                clear(response, AUTH)
            return clear(response, START)
        except (httpx.HTTPError, AuthenticationError, KeyError, ValueError, TypeError):
            return clear(unavailable("We couldn’t finish signing in. Please start again.", 401), START, AUTH)

    @app.post("/delete-account/confirm")
    async def confirm(request: Request):
        auth = read(request, AUTH, SHORT)
        await posted(request, auth)
        await throttle(request, "web-deletion-confirm", 10)
        receipt = read(request, RECEIPT, WEEK)
        if not receipt or receipt.get("account") != auth.get("account"):
            return unavailable("This confirmation has expired. Sign in again.", 401)
        if job := await job_for(receipt):
            return progress(job)
        try:
            p = await identity(auth)
        except AuthenticationError:
            return clear(unavailable("Please sign in again to confirm deletion.", 401), AUTH)
        if receipt["subject_hash"] != subject_hash(p.subject, settings.service_secret):
            return unavailable("This confirmation belongs to a different account.", 403)
        async with db.sessions.begin() as session:
            # A concurrent native request may already have committed with its
            # own receipt. Do not replace that capability or delete other data.
            await lock_account_lifecycle(session, p.subject, settings.service_secret)
            existing = await deletion_for(session, p.subject, settings.service_secret)
            if not existing:
                await request_deletion(session, subject=p.subject, account_id=auth["account"], receipt_secret=receipt["secret"],
                    service_secret=settings.service_secret, now=clock())
        response = headers(RedirectResponse("/delete-account", status_code=303))
        return clear(response, AUTH, START)

    @app.post("/delete-account/cancel")
    async def cancel(request: Request):
        await posted(request, read(request, AUTH, SHORT))
        if job := await job_for(read(request, RECEIPT, WEEK)):
            return progress(job)
        return clear(page("Deletion canceled", '<p class="lead">Your account has not been deleted. You can close this page and continue chatting in Vipi.</p>'), AUTH, START, RECEIPT)
