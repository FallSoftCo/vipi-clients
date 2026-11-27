#!/usr/bin/env python3
"""Bounded real-HTTP/native QA, real WorkOS verifier, isolated PostgreSQL.

Launch on OZZZ-OS under storage-build. Only loopback TCP 48942 is exposed;
authorized SSH/ADB forwards provide the native device paths. No auth bypass.
Create artifacts/network-qa-NNN.stop to finish. Always removes its own database.
"""

import asyncio
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time

ROOT = Path("/aosp/development/vipi")

if sys.argv[1:] == ["--worker"]:
    sys.path.insert(0, str(ROOT / "backend"))
    import uvicorn
    from vipi.api import create_app
    from vipi.config import Settings
    from vipi.db import Database

    settings = Settings()

    async def initialize():
        db = Database(settings.database_url)
        await db.create_for_test()
        await db.close()

    asyncio.run(initialize())
    uvicorn.run(
        create_app(settings),
        host="127.0.0.1",
        port=48942,
        access_log=False,
        log_level="warning",
    )
    raise SystemExit()

assert socket.gethostname() == "ozzz-aosp" and os.geteuid() == 0
revision = sys.argv[1]
assert revision.isdigit() and len(revision) == 3
receipt_path = ROOT / f"artifacts/network-qa-{revision}.json"
assert not receipt_path.exists(), "Use a fresh receipt revision"
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 48942))
run = ROOT / ".runtime" / ("network-qa-" + secrets.token_hex(4))
run.mkdir(mode=0o700)
user = pwd.getpwnam("aosp")
os.chown(run, user.pw_uid, user.pw_gid)
sock = run / "socket"
sock.mkdir(mode=0o777)
sock.chmod(0o777)
password = secrets.token_urlsafe(32)
env_file = run / "postgres.env"
env_file.write_text(
    "POSTGRES_USER=vipi\nPOSTGRES_DB=vipi_qa\nPOSTGRES_PASSWORD="
    + password
    + "\nPOSTGRES_INITDB_ARGS=--auth-local=scram-sha-256 --auth-host=scram-sha-256\n"
)
env_file.chmod(0o600)
name = "vipi-network-qa-" + secrets.token_hex(4)
image = subprocess.check_output(
    ["docker", "image", "inspect", "postgres:16-alpine", "--format", "{{.Id}}"],
    text=True,
).strip()
receipt = {
    "owner": "01a16e0d-ac69-7dd0-872a-8cf087160515",
    "purpose": "isolated native HTTP qualification, real WorkOS authentication",
    "host": "ozzz-aosp",
    "listener": "127.0.0.1:48942",
    "database_network": "none",
    "container": name,
    "image": image,
    "runtime": str(run),
    "started_at": time.time(),
    "deadline": time.time() + 1800,
}
receipt_path.write_text(json.dumps(receipt, indent=2))
stop = ROOT / f"artifacts/network-qa-{revision}.stop"
started = False
worker = None


def terminate(signum, frame):
    raise SystemExit(128 + signum)


signal.signal(signal.SIGTERM, terminate)
try:
    subprocess.run(
        [
            "docker",
            "run",
            "--detach",
            "--name",
            name,
            "--network",
            "none",
            "--memory",
            "256m",
            "--cpus",
            "1",
            "--env-file",
            str(env_file),
            "--mount",
            f"type=bind,src={sock},dst=/var/run/postgresql",
            image,
            "postgres",
            "-c",
            "listen_addresses=",
            "-c",
            "max_connections=40",
            "-c",
            "shared_buffers=32MB",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    started = True
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if (
            subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", "vipi", "-d", "vipi_qa"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        ):
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("PostgreSQL readiness timeout")
    env = os.environ.copy()
    env.update(
        VIPI_DATABASE_URL=f"postgresql+asyncpg://vipi:{password}@/vipi_qa?host={sock}",
        VIPI_WORKOS_CLIENT_ID="client_01M5QPQSVXQDEJGQ1CYZ75MSGS",
        VIPI_WORKOS_ISSUER="https://api.workos.com",
        VIPI_SERVICE_SECRET=secrets.token_urlsafe(32),
        VIPI_ENVIRONMENT="native-qa",
    )
    with (ROOT / f"artifacts/network-qa-{revision}.log").open("w") as output:
        worker = subprocess.Popen(
            [
                "runuser",
                "-u",
                "aosp",
                "--",
                str(ROOT / "backend/.venv/bin/python"),
                __file__,
                "--worker",
            ],
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        receipt["worker_pid"] = worker.pid
        receipt_path.write_text(json.dumps(receipt, indent=2))
        print(
            json.dumps({"receipt": str(receipt_path), "listener": receipt["listener"]}),
            flush=True,
        )
        while not stop.exists() and time.time() < receipt["deadline"]:
            if worker.poll() is not None:
                raise RuntimeError("QA service exited; inspect retained log")
            time.sleep(0.5)
finally:
    if worker and worker.poll() is None:
        worker.terminate()
        try:
            worker.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()
    if started:
        removed = (
            subprocess.run(
                ["docker", "rm", "--force", "--volumes", name],
                stdout=subprocess.DEVNULL,
            ).returncode
            == 0
        )
        receipt["container_removed"] = removed
        if removed:
            shutil.rmtree(run)
    else:
        shutil.rmtree(run)
    receipt["finished_at"] = time.time()
    receipt_path.write_text(json.dumps(receipt, indent=2))
