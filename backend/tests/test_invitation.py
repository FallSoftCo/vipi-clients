"""Public invitation pages need no account lookup or authenticated session."""
import httpx
from html import unescape
from fastapi import FastAPI

from vipi.public_pages import install


async def test_invitation_preserves_name_without_disclosing_a_profile():
    app = FastAPI()
    install(app)  # Deliberately no database, identity service, or user records.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://vipi.test") as client:
        response = await client.get("/invite/Alice_123")
        assert response.status_code == 200
        assert "@alice_123" in response.text
        assert "New chat" in response.text and "username" in response.text
        assert "in testing" in response.text and "after store approval" in response.text
        assert "Set-Cookie" not in response.headers
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"
        assert "<script" not in response.text
        assert "<form" not in response.text
        assert "apps.apple.com" not in response.text and "play.google.com" not in response.text
        # A well-formed but nonexistent username behaves identically. This link
        # never confirms whether a person has an account or exposes their name.
        unknown = await client.get("/invite/nobody_has_this_name")
        assert unknown.status_code == 200
        assert "@nobody_has_this_name" in unknown.text


async def test_invalid_invitation_cannot_inject_content_or_impersonate_system():
    app = FastAPI()
    install(app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://vipi.test") as client:
        for name in ("vbot", "admin", "a", "1alice", "a" * 25, "%3Cscript%3E", "%22onload%3Dalert(1)"):
            response = await client.get("/invite/" + name)
            assert response.status_code == 404
            assert "This invitation isn't valid" in unescape(response.text)
            assert "<script>" not in response.text and "onload=" not in response.text
            assert response.headers["X-Robots-Tag"].startswith("noindex")
