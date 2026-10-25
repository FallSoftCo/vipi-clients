import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from vipi.auth import AuthenticationError, WorkOSVerifier
from vipi.config import Settings


@pytest.fixture
def signing():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    public.update(kid="fixture", alg="RS256", use="sig")
    return private, public


def claims(**changes):
    now = int(time.time())
    return dict(iss="https://api.workos.com", sub="user_fixture", sid="session_fixture",
                client_id="client_fixture", iat=now, exp=now + 300, auth_time=now) | changes


def verifier(signing, handler=None):
    settings = Settings(database_url="sqlite+aiosqlite://", workos_client_id="client_fixture",
                        workos_issuer="https://api.workos.com", service_secret="a" * 43)
    return WorkOSVerifier(settings, transport=httpx.MockTransport(handler or (
        lambda request: httpx.Response(200, json={"keys": [signing[1]]}))))


async def test_valid_token_binds_application_even_without_audience(signing):
    v = verifier(signing)
    try:
        token = jwt.encode(claims(), signing[0], algorithm="RS256", headers={"kid": "fixture"})
        assert (await v.verify(token)).subject == "user_fixture"
        for patch in ({"client_id": "client_other"}, {"iss": "https://attacker.invalid"},
                      {"exp": int(time.time()) - 60}, {"iat": int(time.time()) + 60},
                      {"sub": "admin"}, {"auth_time": "yesterday"},
                      {"exp": int(time.time()) + 3601}, {"exp": str(int(time.time()) + 300)}):
            with pytest.raises(AuthenticationError):
                await v.verify(jwt.encode(claims(**patch), signing[0], algorithm="RS256", headers={"kid": "fixture"}))
    finally:
        await v.close()


async def test_wrong_signature_missing_claims_and_algorithm_rejected(signing):
    v = verifier(signing)
    try:
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        incomplete = claims(); del incomplete["client_id"]
        tokens = [jwt.encode(claims(), other, algorithm="RS256", headers={"kid": "fixture"}),
                  jwt.encode(incomplete, signing[0], algorithm="RS256", headers={"kid": "fixture"}),
                  jwt.encode(claims(), "a" * 64, algorithm="HS256", headers={"kid": "fixture"}),
                  jwt.encode(claims(), key="", algorithm="none", headers={"kid": "fixture"})]
        for token in tokens:
            with pytest.raises(AuthenticationError):
                await v.verify(token)
    finally:
        await v.close()


async def test_unknown_key_is_bounded_and_outage_fails_closed(signing):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"keys": [signing[1]]})
    v = verifier(signing, respond)
    try:
        for i in range(10):
            token = jwt.encode(claims(), signing[0], algorithm="RS256", headers={"kid": f"unknown-{i}"})
            with pytest.raises(AuthenticationError):
                await v.verify(token)
        assert len(calls) == 1
        valid = jwt.encode(claims(), signing[0], algorithm="RS256", headers={"kid": "fixture"})
        assert (await v.verify(valid)).subject == "user_fixture"
        v.loaded_at -= 301
        with pytest.raises(AuthenticationError):
            await v.verify(valid)
    finally:
        await v.close()
