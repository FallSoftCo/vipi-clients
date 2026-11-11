#!/usr/bin/env python3
"""Reconcile a NEW, offline SQLite copy; never accepts a database service URL.

Production PostgreSQL restoration/reopening is deliberately not implemented.
Evidence/DB are private files; stdout contains no account identifiers or secrets.
"""
import argparse
import asyncio
from datetime import datetime, UTC
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from uuid import uuid4

from sqlalchemy.engine import URL

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from vipi.db import Database
from vipi.recovery import BoundRecoveryEvidence, reconcile_marked_offline
from vipi.recovery_admission import mark_restore


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(part)
    return value.hexdigest()


async def run(args):
    os.umask(0o077)
    source, supplied, output = args.snapshot, args.evidence, args.output
    if source.is_symlink() or supplied.is_symlink() or not source.is_file() or not supplied.is_file():
        raise ValueError("regular offline inputs required")
    if source.stat().st_size > 256 * 1024**2 or supplied.stat().st_size > 4 * 1024**2:
        raise ValueError("input bounds exceeded")
    if any(Path(str(source) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("uncheckpointed or active SQLite input refused")
    bound = BoundRecoveryEvidence.model_validate_json(supplied.read_bytes())
    evidence = bound.reconciliation
    before = digest(source)
    if before != evidence.snapshot_sha256:
        raise ValueError("snapshot hash mismatch")
    if shutil.disk_usage(output.parent).free < 8 * 1024**3 + source.stat().st_size * 3 + 8 * 1024**2:
        raise ValueError("disk reserve unavailable")
    output.mkdir(mode=0o700, exist_ok=False)
    receipt = {"complete": False, "reopen_authorized": False,
               "source_sha256": before, "supplied_file_sha256": digest(supplied),
               "scope": "new offline SQLite copy only; no service/provider calls"}
    db = None
    try:
        # Durable intent precedes copying; final target name is published only
        # after a committed database-local HOLD. Failed staging is never served.
        intent = {"state": "HOLD", "restore_id": str(uuid4()), "snapshot_sha256": before}
        with (output / "HOLD.json").open("x") as f:
            json.dump(intent, f); f.flush(); os.fsync(f.fileno())
        directory = os.open(output, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
        target = output / ".restoring.sqlite"
        with source.open("rb") as src, target.open("xb") as dst:
            shutil.copyfileobj(src, dst)
            dst.flush(); os.fsync(dst.fileno())
        if digest(target) != before or digest(source) != before:
            raise ValueError("source changed during copying")
        db = Database(URL.create("sqlite+aiosqlite", database=str(target.resolve())), offline_recovery=True)
        await mark_restore(db, snapshot_sha256=before, snapshot_at=evidence.snapshot_at, restore_id=intent["restore_id"])
        await db.close(); db = None
        with target.open("rb") as f: os.fsync(f.fileno())
        final = output / "quarantined.sqlite"
        target.rename(final); target = final
        directory = os.open(output, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
        with sqlite3.connect(target.resolve().as_uri() + "?mode=ro", uri=True) as check:
            if check.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ValueError("invalid SQLite snapshot")
        db = Database(URL.create("sqlite+aiosqlite", database=str(target.resolve())), offline_recovery=True)
        report = await reconcile_marked_offline(db, bound, now=datetime.now(UTC))
        await db.close()
        db = None
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        receipt.update(complete=True, output_sha256=digest(target), source_unchanged=digest(source) == before,
                       report_sha256=digest(output / "report.json"))
    except Exception as error:
        # Never serialize SQL parameters, identity records, URLs or provider data.
        receipt["error_type"] = type(error).__name__
        raise
    finally:
        if db is not None:
            await db.close()
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"complete": True, "reopen_authorized": False, "runtime_gate_installed": True}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    try:
        asyncio.run(run(parser.parse_args()))
    except Exception as error:
        print(json.dumps({"complete": False, "reopen_authorized": False, "error_type": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)
