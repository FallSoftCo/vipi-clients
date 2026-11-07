"""Verify WorkOS access tokens against the pinned application's JWKS.

WorkOS access tokens currently bind the application using client_id, not aud.
No unverified claim selects an issuer, URL, algorithm or application.
"""
import asyncio
import time
from dataclasses import dataclass

import httpx
import jwt

from .config import Settings


class AuthenticationError(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    subject: str
    session_id: str
    authenticated_at: int


class RSAKeyCache:
    """Bounded key retrieval from a caller-pinned HTTPS endpoint."""
    def __init__(self, jwks_url: str, *, transport=None):
        self.jwks_url = jwks_url
        self.http = httpx.AsyncClient(timeout=8, follow_redirects=False, transport=transport)
        self.keys: dict[str, jwt.PyJWK] = {}
        self.loaded_at = 0.0
        self.attempted_at = float("-inf")
        self.lock = asyncio.Lock()

    async def close(self):
        await self.http.aclose()

    async def _key(self, kid: str):
        async with self.lock:
            now = time.monotonic()
            if now - self.loaded_at < 300 and kid in self.keys:
                return self.keys[kid].key
            # Unknown-kid attacks cannot turn every request into a WorkOS call.
            if now - self.attempted_at < 30:
                raise AuthenticationError("sign_in_required")
            self.attempted_at = now
            try:
                async with self.http.stream("GET", self.jwks_url) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 65_536:
                            raise ValueError("oversized_jwks")
                import json
                document = json.loads(body)
                keys = {}
                for item in document["keys"]:
                    if item.get("kty") != "RSA" or item.get("alg", "RS256") != "RS256" or item.get("use", "sig") != "sig":
                        continue
                    name = item.get("kid")
                    if not isinstance(name, str) or not 1 <= len(name) <= 200 or name in keys:
                        raise ValueError("invalid_key_id")
                    parsed = jwt.PyJWK.from_dict(item, algorithm="RS256")
                    if parsed.key.key_size < 2048:
                        raise ValueError("weak_key")
                    keys[name] = parsed
                if not keys or len(keys) > 20:
                    raise ValueError("invalid_key_set")
                self.keys, self.loaded_at = keys, time.monotonic()
            except (httpx.HTTPError, ValueError, KeyError, TypeError, jwt.PyJWTError) as error:
                raise AuthenticationError("sign_in_required") from error
            if kid not in self.keys:
                raise AuthenticationError("sign_in_required")
            return self.keys[kid].key

class WorkOSVerifier(RSAKeyCache):
    def __init__(self, settings: Settings, *, transport=None):
        super().__init__(settings.jwks_url, transport=transport)
        self.settings = settings

    async def verify(self, token: str) -> Principal:
        try:
            if not 32 <= len(token) <= 16_384:
                raise ValueError("invalid_token_size")
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if header.get("alg") != "RS256" or not isinstance(kid, str) or not 1 <= len(kid) <= 200:
                raise ValueError("invalid_header")
            claims = jwt.decode(token, await self._key(kid), algorithms=["RS256"],
                issuer=self.settings.workos_issuer, leeway=15,
                options={"require": ["iss", "sub", "sid", "exp", "iat", "client_id", "auth_time"],
                         "verify_aud": False})
            if claims["client_id"] != self.settings.workos_client_id:
                raise ValueError("wrong_application")
            if type(claims["exp"]) is not int or type(claims["iat"]) is not int or not 0 < claims["exp"] - claims["iat"] <= 3600:
                raise ValueError("invalid_access_token_lifetime")
            if not isinstance(claims["sub"], str) or not claims["sub"].startswith("user_") or len(claims["sub"]) > 128:
                raise ValueError("invalid_subject")
            if not isinstance(claims["sid"], str) or not 1 <= len(claims["sid"]) <= 128:
                raise ValueError("invalid_session")
            if type(claims["auth_time"]) is not int or claims["auth_time"] > int(time.time()) + 15:
                raise ValueError("invalid_authentication_time")
            return Principal(claims["sub"], claims["sid"], claims["auth_time"])
        except (ValueError, KeyError, TypeError, jwt.PyJWTError) as error:
            raise AuthenticationError("sign_in_required") from error
