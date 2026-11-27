"""Opt-in startup recovery hold. No evidence report can release this boundary."""

from pathlib import Path

from fastapi import FastAPI
from starlette.responses import HTMLResponse, JSONResponse, Response

from .delivery import DeliveryError

SAFE_STATIC_PATHS = frozenset(
    {
        "/",
        "/privacy",
        "/terms",
        "/vipi-legal.css",
        "/help",
        "/delete-account",
        "/delete-account/style.css",
    }
)


def require_not_held(settings):
    if settings.recovery_hold:
        raise DeliveryError("recovery_hold", 503)


class RecoveryBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            await send(
                {"type": "websocket.close", "code": 1013, "reason": "recovery_hold"}
            )
            return
        if scope["type"] == "http":
            path, method = scope.get("path", ""), scope.get("method", "")
            if method in {"GET", "HEAD"} and (
                path in SAFE_STATIC_PATHS or path == "/health/live"
            ):
                await self.app(scope, receive, send)
                return
            # Includes readiness and every state/API/auth/provider callback path.
            response = JSONResponse(
                {"error": "recovery_hold", "status": "recovery_hold"},
                status_code=503,
                headers={"Cache-Control": "no-store", "Retry-After": "60"},
            )
            if method == "HEAD":
                response.body = b""
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def held_application():
    """No database/verifier/provider constructors or background listener startup."""
    from .public_pages import install

    app = FastAPI(
        title="Vipi recovery hold", docs_url=None, redoc_url=None, openapi_url=None
    )
    install(app)
    # HEAD is explicitly read-only here; default deployment routes are unchanged.
    for route in app.routes:
        if route.path in SAFE_STATIC_PATHS and "GET" in route.methods:
            route.methods.add("HEAD")

    @app.api_route("/health/live", methods=["GET", "HEAD"])
    async def live():
        return {"status": "ok"}

    @app.api_route("/delete-account/style.css", methods=["GET", "HEAD"])
    async def css():
        return Response(
            Path(__file__).with_name("deletion.css").read_text(),
            media_type="text/css",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.api_route("/delete-account", methods=["GET", "HEAD"])
    async def deletion_guidance():
        return HTMLResponse(
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>Vipi account deletion during recovery</title><body><main>"
            "<h1>Account deletion during service recovery</h1>"
            "<p>The service is temporarily held for recovery. Online sign-in and account changes are unavailable. "
            "This page does not submit or confirm a deletion request.</p>"
            '<p>For account deletion help, contact <a href="mailto:one@fallsoft.co">one@fallsoft.co</a>. '
            "Do not send passwords or device credentials.</p>"
            "<p>Deleting an account does not cancel store subscriptions. Manage them in "
            '<a href="https://apps.apple.com/account/subscriptions">Apple subscription settings</a> or '
            '<a href="https://play.google.com/store/account/subscriptions">Google Play subscriptions</a>. '
            "Friends’ copies and backups you saved separately are not erased by account deletion.</p>"
            '<p><a href="/privacy">Privacy</a> · <a href="/help">Help</a></p></main></body></html>',
            headers={
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            },
        )

    app.add_middleware(RecoveryBoundary)
    return app
