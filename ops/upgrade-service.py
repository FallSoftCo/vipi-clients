#!/usr/bin/env python3
"""Activate a prebuilt, schema-compatible Vipi release with automatic rollback.

Only vipi-api.service is restarted. No dependency installation, shared service
restart, configuration mutation, database migration or network change.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def verify_release(release, revision):
    require(release.is_dir() and not release.is_symlink(), "Release must be an ordinary directory")
    manifest = json.loads((release / "manifest.json").read_text())
    require(manifest["revision"] == revision, "Manifest revision mismatch")
    for name, digest in manifest["files"].items():
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts, "Unsafe manifest path")
        path = release / relative
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(release), "Invalid release file")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, f"Hash mismatch: {name}")
    actual = {str(p.relative_to(release)) for p in release.rglob("*") if p.is_file()}
    require(actual == set(manifest["files"]) | {"manifest.json"}, "Unexpected release files")
    return manifest


def fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=4) as response:
            return {"status": response.status, "body": response.read(1024).decode()}
    except urllib.error.HTTPError as error:
        return {"status": error.code}


def healthy():
    response = fetch("http://127.0.0.1:48943/health/ready")
    return response["status"] == 200 and json.loads(response["body"]) == {"status": "ok"}


def shared_services():
    return {unit: subprocess.check_output(["systemctl", "show", unit, "--property=ActiveState,MainPID,ActiveEnterTimestampMonotonic"], text=True).strip()
            for unit in ("nginx.service", "postgresql@16-main.service")}


def activate(target):
    link = Path("/opt/vipi/current.next")
    require(not link.exists() and not link.is_symlink(), "Another activation may be in progress")
    link.symlink_to(target)
    os.replace(link, "/opt/vipi/current")
    subprocess.run(["systemctl", "restart", "vipi-api.service"], check=True, timeout=45)
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        try:
            if healthy():
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    raise RuntimeError("Vipi readiness did not recover")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision")
    parser.add_argument("--expected-current", required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    require(socket.gethostname() == "fallsoft-production-20261106" and os.geteuid() == 0, "Wrong host or user")
    for value in (args.revision, args.expected_current):
        require(re.fullmatch(r"[0-9a-f]{40}", value), "Invalid revision")
    releases = Path("/opt/vipi/releases")
    current = Path("/opt/vipi/current")
    old = releases / args.expected_current
    new = releases / args.revision
    require(current.is_symlink() and current.resolve() == old, "Current release changed")
    require(new != old, "Already on requested release")
    previous = verify_release(old, args.expected_current)
    manifest = verify_release(new, args.revision)
    migration_files = lambda data: {k: v for k, v in data["files"].items() if k.startswith("migrations/") or k == "alembic.ini"}
    require(migration_files(previous) == migration_files(manifest), "Schema change requires a separate migration plan")
    for unit in ("vipi-api.service", "vipi-expiry.service", "vipi-expiry.timer"):
        require((Path("/etc/systemd/system") / unit).read_bytes() == (new / "ops" / unit).read_bytes(), "Unit change requires separate installation")
    require(healthy(), "Existing service is not ready")
    require(fetch("https://api.mambovipi.app/health/live")["status"] == 200, "Public health failed")
    require(fetch("https://api.mambovipi.app/health/ready")["status"] == 403, "Readiness must remain private")
    require(fetch("https://api.mambovipi.app/v1/me")["status"] == 401, "Authentication must remain enforced")
    before = shared_services()
    if args.verify_only:
        print(json.dumps({"verified": args.revision, "current": args.expected_current, "schema_unchanged": True}))
        return
    record_dir = Path("/opt/vipi/deployments")
    record_dir.mkdir(mode=0o700, exist_ok=True)
    record = record_dir / f"{args.revision}.json"
    require(not record.exists(), "Preserve previous deployment receipt")
    receipt = {"owner": "01a16e0d-ac69-7dd0-872a-8cf087160515", "host": socket.gethostname(),
               "started": datetime.now(timezone.utc).isoformat(), "old": args.expected_current,
               "new": args.revision, "schema_unchanged": True, "shared_before": before, "state": "prepared"}
    def save():
        temporary = record.with_suffix(".tmp")
        with open(temporary, "w", opener=lambda path, flags: os.open(path, flags, 0o600)) as output:
            json.dump(receipt, output, indent=2); output.write("\n"); output.flush(); os.fsync(output.fileno())
        os.replace(temporary, record)
    save()
    try:
        activate(new)
        require(fetch("https://api.mambovipi.app/health/live")["status"] == 200, "Public health failed after activation")
        require(fetch("https://api.mambovipi.app/v1/me")["status"] == 401, "Authentication changed")
        receipt["shared_after"] = shared_services()
        require(receipt["shared_after"] == before, "Shared service state changed during deployment")
        receipt["state"] = "active_verified"
    except BaseException as error:
        receipt["failure"] = type(error).__name__ + ": " + str(error)
        receipt["state"] = "rolling_back"; save()
        try:
            activate(old)
            receipt["state"] = "rolled_back_verified"
        except BaseException as rollback_error:
            receipt["state"] = "rollback_failed"
            receipt["rollback_error"] = str(rollback_error)
        save()
        raise
    receipt["finished"] = datetime.now(timezone.utc).isoformat(); save()
    print(json.dumps({"receipt": str(record), "state": receipt["state"], "revision": args.revision}))


if __name__ == "__main__":
    main()
