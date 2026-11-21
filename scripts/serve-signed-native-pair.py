#!/usr/bin/env python3
"""Explicit local test authentication + normal Vipi API, never production auth.

Ephemeral RSA signing key stays in this process. Two fresh local credentials
are written under the NEW private run directory; no customer/provider secret
is read. The native test-only transport uses these JWTs over owned loopback.
"""
import argparse
import asyncio
from contextlib import nullcontext
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Request
from starlette.responses import JSONResponse
import uvicorn
from vipi.api import create_app
from vipi.auth import WorkOSVerifier
from vipi.db import Database
from vipi.identity_authorities import IdentityAuthority


def load_settings(directory, subjects):
    spec = importlib.util.spec_from_file_location("native_pair_settings", Path(__file__).with_name("serve-isolated-native-pair.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.settings_for(directory, subjects).model_copy(update={
        "shared_identity_transition_enabled": False,
        "workos_client_id": "client_local_native_pair", "workos_issuer": "http://127.0.0.1:48944/qa-auth"})


async def serve(args):
    directory = args.run_directory.resolve()
    directory.mkdir(mode=0o700)
    suffix = secrets.token_hex(6)
    credentials = {name: {"username": f"vqa_{name}_{suffix}", "password": secrets.token_urlsafe(32),
        "subject": f"user_localpair_{name}_{suffix}"} for name in ("android", "ios")}
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk.update(kid="local-native-pair-" + suffix, alg="RS256", use="sig")
    origin = f"http://127.0.0.1:{args.port}"
    authority = IdentityAuthority("local-native-pair-test", "client_local_native_pair", origin + "/qa-auth", origin + "/qa-auth/jwks")
    settings = load_settings(directory, [c["subject"] for c in credentials.values()]).model_copy(update={"workos_issuer": authority.issuer})
    if args.media:
        settings = settings.model_copy(update={"media_enabled": True, "media_storage_path": str(directory / "opaque-media")})
    db = Database(settings.database_url)
    await db.create_for_test()
    verifier = WorkOSVerifier(settings, authority=authority)
    app = create_app(settings, database=db, verifier=verifier)
    auth_counts = {"successful": 0, "rejected": 0}

    @app.get("/qa-auth/jwks")
    async def jwks():
        return {"keys": [jwk]}

    @app.post("/qa-auth/token")
    async def token(request: Request):
        value = await request.json()
        match = next((c for c in credentials.values() if secrets.compare_digest(str(value.get("username", "")), c["username"]) and
            secrets.compare_digest(str(value.get("password", "")), c["password"])), None)
        if match is None:
            auth_counts["rejected"] += 1
            return JSONResponse({"error": "invalid_test_credentials"}, status_code=401)
        now = int(time.time())
        claims = {"iss": authority.issuer, "client_id": authority.client_id, "sub": match["subject"],
            "sid": "session_local_" + secrets.token_hex(12), "iat": now, "exp": now + 3600, "auth_time": now}
        auth_counts["successful"] += 1
        return {"access_token": jwt.encode(claims, key, algorithm="RS256", headers={"kid": jwk["kid"]}),
            "token_type": "Bearer", "expires_in": 3600, "subject": match["subject"]}

    (directory / "local-test-credentials.json").write_text(json.dumps(credentials, indent=2) + "\n")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning"))
    server.capture_signals = nullcontext
    previous = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    for signum in previous:
        signal.signal(signum, lambda *_: setattr(server, "should_exit", True))
    receipt = {"purpose": "explicit synthetic authentication; not WorkOS or owner conversation proof", "started_at": datetime.now(UTC).isoformat(),
        "pid": os.getpid(), "source_revision": args.source_revision, "endpoint": origin, "database": "new isolated SQLite",
        "normal_api": True, "media": args.media, "verifier": "production WorkOSVerifier class with explicit test-only loopback authority and ephemeral RS256 key",
        "jwks_public_sha256": hashlib.sha256(json.dumps(jwk, sort_keys=True).encode()).hexdigest(),
        "production_auth_modified": False, "paid_or_push_provider_credentials": False, "deadline_seconds": args.seconds}
    path = directory / "server-receipt.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    async def expire():
        await asyncio.sleep(args.seconds)
        server.should_exit = True
    timer = asyncio.create_task(expire())
    try:
        await server.serve()
    finally:
        timer.cancel()
        await verifier.close()
        await db.close()
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        with socket.socket() as probe:
            closed = probe.connect_ex(("127.0.0.1", args.port)) != 0
        receipt.update(finished_at=datetime.now(UTC).isoformat(), listener_closed=closed, authentication_counts=auth_counts)
        path.write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--media", action="store_true", help="Enable encrypted media in this private fixture")
    parser.add_argument("--port", type=int, default=48944)
    parser.add_argument("--seconds", type=int, default=1800)
    args = parser.parse_args()
    assert 1024 <= args.port <= 65535 and 30 <= args.seconds <= 1800
    os.umask(0o077)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", args.port))
    asyncio.run(serve(args))
