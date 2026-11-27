#!/usr/bin/env python3
"""Fresh local test identities + real normal-auth groups API. No live authority.

Only loopback HTTP and a caller-owned fresh Unix PostgreSQL database are allowed.
RSA private key lives only in memory; credentials are private, scoped and synthetic.
"""

import argparse, asyncio, hashlib, json, os, secrets, signal, socket, sys, time
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import jwt, uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Request
from starlette.responses import JSONResponse
from sqlalchemy.engine import make_url
from vipi.api import create_app
from vipi.auth import WorkOSVerifier
from vipi.config import Settings
from vipi.db import Database
from vipi.identity_authorities import IdentityAuthority


async def serve(args):
    directory = args.run_directory.resolve()
    assert str(directory).startswith(
        "/mnt/extradrive1/vipi-builds/groups-native-three-r01/"
    )
    url = make_url(args.database_url)
    assert url.drivername == "postgresql+asyncpg" and not url.host and not url.password
    assert url.database.startswith("vipi_groups_native_")
    assert str(url.query.get("host", "")).startswith("/mnt/extradrive1/vipi-builds/")
    assert not directory.exists(), (
        "New run directory required; inspect original receipts before any repeat"
    )
    directory.mkdir(mode=0o700)
    suffix = secrets.token_hex(6)
    credentials = {
        role: {
            "username": f"vqa_{role}_{suffix}",
            "password": secrets.token_urlsafe(32),
            "subject": f"user_localgroups_{role}_{suffix}",
        }
        for role in ("alice", "bob", "carol")
    }
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk.update(kid="local-native-groups-" + suffix, alg="RS256", use="sig")
    origin = f"http://127.0.0.1:{args.port}"
    authority = IdentityAuthority(
        "local-native-groups-test",
        "client_localnativegroups",
        origin + "/qa-auth",
        origin + "/qa-auth/jwks",
    )
    settings = Settings(
        _env_file=None,
        _env_prefix="VIPI_GROUPS_QA_DISABLED_",
        database_url=args.database_url,
        workos_client_id=authority.client_id,
        workos_issuer=authority.issuer,
        service_secret=secrets.token_urlsafe(32),
        environment="native-qa",
        allowed_subjects=frozenset(c["subject"] for c in credentials.values()),
        groups_enabled=True,
    )
    assert (
        not settings.shared_identity_transition_enabled
        and not settings.enforce_subscriptions
    )
    assert not any(
        (
            settings.workos_api_key,
            settings.deepseek_api_key,
            settings.apns_private_key_path,
            settings.fcm_service_account_path,
        )
    )
    db = Database(settings.database_url)
    await db.create_for_test()
    verifier = WorkOSVerifier(settings, authority=authority)
    app = create_app(settings, database=db, verifier=verifier)
    counts = {"successful": 0, "rejected": 0}

    @app.get("/qa-auth/jwks")
    async def jwks():
        return {"keys": [jwk]}

    @app.post("/qa-auth/token")
    async def token(request: Request):
        value = await request.json()
        match = next(
            (
                c
                for c in credentials.values()
                if secrets.compare_digest(str(value.get("username", "")), c["username"])
                and secrets.compare_digest(
                    str(value.get("password", "")), c["password"]
                )
            ),
            None,
        )
        if match is None:
            counts["rejected"] += 1
            return JSONResponse({"error": "invalid_test_credentials"}, status_code=401)
        now = int(time.time())
        counts["successful"] += 1
        claims = {
            "iss": authority.issuer,
            "client_id": authority.client_id,
            "sub": match["subject"],
            "sid": "session_local_" + secrets.token_hex(12),
            "iat": now,
            "exp": now + 3600,
            "auth_time": now,
        }
        return {
            "access_token": jwt.encode(
                claims, key, algorithm="RS256", headers={"kid": jwk["kid"]}
            ),
            "subject": match["subject"],
            "expires_in": 3600,
        }

    (directory / "local-test-credentials.json").write_text(
        json.dumps(credentials, indent=2) + "\n"
    )
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning"
        )
    )
    server.capture_signals = nullcontext
    old = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    for signum in old:
        signal.signal(signum, lambda *_: setattr(server, "should_exit", True))
    receipt = {
        "purpose": "three-member native groups API/Signal fixture; not owner/hosted sign-up/UI proof",
        "pid": os.getpid(),
        "source_revision": args.source_revision,
        "endpoint": origin,
        "started_at": datetime.now(UTC).isoformat(),
        "database": "fresh private Unix-only PostgreSQL",
        "normal_api": True,
        "real_verifier": "WorkOSVerifier with explicit test authority and ephemeral RS256 JWKS",
        "groups_enabled_only_in_fixture": True,
        "production_auth_modified": False,
        "paid_or_push_provider_credentials": False,
        "native_private_keys_exported": False,
        "deadline_seconds": args.seconds,
        "jwks_public_sha256": hashlib.sha256(
            json.dumps(jwk, sort_keys=True).encode()
        ).hexdigest(),
    }
    path = directory / "server-receipt.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n")

    async def deadline():
        await asyncio.sleep(args.seconds)
        server.should_exit = True

    timer = asyncio.create_task(deadline())
    try:
        await server.serve()
    finally:
        timer.cancel()
        await verifier.close()
        await db.close()
        for signum, handler in old.items():
            signal.signal(signum, handler)
        with socket.socket() as probe:
            closed = probe.connect_ex(("127.0.0.1", args.port)) != 0
        receipt.update(
            finished_at=datetime.now(UTC).isoformat(),
            listener_closed=closed,
            authentication_counts=counts,
        )
        path.write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--port", type=int, default=48956)
    parser.add_argument("--seconds", type=int, default=1200)
    args = parser.parse_args()
    assert 1024 <= args.port <= 65535 and 30 <= args.seconds <= 1800
    os.umask(0o077)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", args.port))
    asyncio.run(serve(args))
