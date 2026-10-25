#!/usr/bin/env python3
"""Run isolated PostgreSQL tests on OZZZ-OS, inside storage-build admission.

Uses the existing local image. No TCP listener, no shared database, no image pull.
The private database and container are removed after the retained test receipt.
"""
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import socket
import subprocess
import time
import sys
import argparse


assert socket.gethostname() == "ozzz-aosp" and os.geteuid() == 0
root = Path("/aosp/development/vipi")
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("revision", help="Three-digit, unused receipt number")
args = parser.parse_args()
revision = args.revision
assert revision.isdigit() and len(revision) == 3
log = root / "artifacts" / f"backend-postgres-{revision}.log"
assert not log.exists() and not (root / f"artifacts/backend-postgres-{revision}.json").exists(), "Preserve prior receipts"
image = subprocess.check_output(["docker", "image", "inspect", "postgres:16-alpine", "--format", "{{.Id}}"], text=True).strip()
run = root / ".runtime" / ("postgres-qa-" + secrets.token_hex(4))
run.mkdir(mode=0o700, parents=True)
user = pwd.getpwnam("aosp")
os.chown(run, user.pw_uid, user.pw_gid)
sock = run / "socket"
sock.mkdir(mode=0o777)
sock.chmod(0o777)
env_file = run / "postgres.env"
password = secrets.token_urlsafe(32)
env_file.write_text("POSTGRES_USER=vipi\nPOSTGRES_DB=vipi_qa\nPOSTGRES_PASSWORD=" + password + "\nPOSTGRES_INITDB_ARGS=--auth-local=scram-sha-256 --auth-host=scram-sha-256\n")
env_file.chmod(0o600)
name = "vipi-postgres-qa-" + secrets.token_hex(4)
receipt = {"container": name, "image": image, "network": "none", "socket_only": True, "started_at": time.time()}
started = False
try:
    subprocess.run(["docker", "run", "--detach", "--name", name, "--network", "none", "--memory", "256m", "--cpus", "1",
        "--env-file", str(env_file), "--mount", f"type=bind,src={sock},dst=/var/run/postgresql", image,
        "postgres", "-c", "listen_addresses=", "-c", "max_connections=40", "-c", "shared_buffers=32MB"],
        check=True, stdout=subprocess.DEVNULL)
    started = True
    # Readiness runs inside this process, with a bounded deadline.
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        result = subprocess.run(["docker", "exec", name, "pg_isready", "-U", "vipi", "-d", "vipi_qa"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("isolated PostgreSQL did not become ready")
    env = os.environ.copy()
    env["VIPI_TEST_POSTGRES_URL"] = f"postgresql+asyncpg://vipi:{password}@/vipi_qa?host={sock}"
    with log.open("w") as output:
        result = subprocess.run(["runuser", "-u", "aosp", "--", str(root / "backend/.venv/bin/pytest"), "-q"],
            cwd=root / "backend", env=env, stdout=output, stderr=subprocess.STDOUT)
    receipt["test_exit_code"] = result.returncode
    print(json.dumps({"test_exit_code": result.returncode, "log": str(log)}))
finally:
    if started:
        cleanup = subprocess.run(["docker", "rm", "--force", "--volumes", name], stdout=subprocess.DEVNULL)
        receipt["container_removed"] = cleanup.returncode == 0
        if cleanup.returncode == 0:
            shutil.rmtree(run)
    else:
        shutil.rmtree(run)
    receipt["finished_at"] = time.time()
    (root / f"artifacts/backend-postgres-{revision}.json").write_text(json.dumps(receipt, indent=2) + "\n")
if receipt.get("test_exit_code") != 0 or not receipt.get("container_removed"):
    raise SystemExit(1)
