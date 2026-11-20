#!/usr/bin/env python3
"""Real WorkOS + real Vipi HTTP relay, with a fresh local SQLite QA database.

No provider admin key, auth bypass, push provider, billing or production access.
Expose loopback only. Native clients use their existing owned QA login through
explicit forwards. Invoke once per run directory; never resumes uncertain work.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import sys
from datetime import UTC, datetime
from contextlib import nullcontext

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from vipi.api import create_app
from vipi.config import Settings
from vipi.db import Database
from vipi.identity_authorities import FALLSOFT_VIPI
import uvicorn


def settings_for(directory, subjects):
    # Explicit constructor arguments keep live VIPI_* settings out of this run.
    return Settings(_env_file=None, _env_prefix="VIPI_PAIR_DISABLED_", database_url=f"sqlite+aiosqlite:///{directory / 'pair.sqlite'}",
        workos_client_id=FALLSOFT_VIPI.client_id, workos_issuer=FALLSOFT_VIPI.issuer,
        shared_identity_transition_enabled=True, service_secret=secrets.token_urlsafe(32),
        environment="native-qa", allowed_subjects=frozenset(subjects),
        enforce_subscriptions=False, reviewer_user_ids=frozenset(), reviewer_identity_subjects=frozenset(),
        store_sandbox_user_ids=frozenset(), store_sandbox_restricted=False,
        account_deletion_enabled=False, global_deletion_enabled=False,
        workos_api_key=None, global_deletion_secret=None, deletion_web_origin=None,
        apple_key_id=None, apple_issuer_id=None, apple_private_key_path=None, apple_root_certificate_paths=(),
        google_service_account_path=None, google_rtdn_audience=None, google_rtdn_service_account=None,
        google_rtdn_subscription=None, google_allow_test_purchases=False, deepseek_api_key=None,
        fcm_project_id=None, fcm_service_account_path=None, apns_key_id=None, apns_team_id=None,
        apns_private_key_path=None, apns_sandbox_key_id=None, apns_sandbox_private_key_path=None)


async def serve(args):
    directory = args.run_directory.resolve()
    # Separate immutable run paths stop accidental replay and retained DB reuse.
    directory.mkdir(mode=0o700)
    subjects = json.loads(args.subjects_file.read_text())
    assert isinstance(subjects, list) and len(subjects) == 2 and len(set(subjects)) == 2
    assert all(isinstance(s, str) and s.startswith("fallsoft-vipi-production:user_") for s in subjects)
    settings = settings_for(directory, subjects)
    db = Database(settings.database_url)
    await db.create_for_test()
    server = uvicorn.Server(uvicorn.Config(create_app(settings, database=db),
        host="127.0.0.1", port=args.port, access_log=False, log_level="warning"))
    # Uvicorn re-raises SIGTERM after its lifespan closes, which would skip
    # our final receipt. Own these two handlers and request graceful shutdown.
    server.capture_signals = nullcontext
    previous_handlers = {signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)}
    for signum in previous_handlers:
        signal.signal(signum, lambda *_: setattr(server, "should_exit", True))
    receipt = {"started_at": datetime.now(UTC).isoformat(), "host": socket.gethostname(),
        "pid": os.getpid(), "endpoint": f"http://127.0.0.1:{args.port}", "database": "isolated SQLite",
        "source_revision": args.source_revision, "real_workos_verifier": True,
        "verified_subject_allowlist_count": 2, "push_providers_configured": False,
        "paid_dependencies_configured": False, "deadline_seconds": args.seconds,
        "proof_boundary": "real HTTP/backend/native libsignal when native stages complete; not production PostgreSQL, hosted signup or APNs/FCM"}
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
        await db.close()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        with socket.socket() as probe:
            closed = probe.connect_ex(("127.0.0.1", args.port)) != 0
        receipt.update(finished_at=datetime.now(UTC).isoformat(), listener_closed=closed,
            retained_database=str(directory / "pair.sqlite"))
        path.write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--subjects-file", type=Path, required=True, help="Private JSON array of two canonical verified QA subjects; no tokens")
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--port", type=int, default=48944)
    parser.add_argument("--seconds", type=int, default=1800)
    args = parser.parse_args()
    assert 1024 <= args.port <= 65535 and 30 <= args.seconds <= 1800
    os.umask(0o077)
    # Probe before creating receipts, so an occupied endpoint never starts a run.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", args.port))
    asyncio.run(serve(args))
