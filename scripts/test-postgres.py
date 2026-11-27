#!/usr/bin/env python3
"""Run backend tests against a disposable local PostgreSQL 16 cluster."""

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
from datetime import UTC, datetime
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
PORT = 5432


def run(args):
    directory = args.run_directory.resolve()
    socket_dir = directory / "socket"
    if len(os.fsencode(socket_dir / f".s.PGSQL.{PORT}")) > 100:
        raise SystemExit("Choose a shorter run directory for the PostgreSQL socket.")
    if os.geteuid() == 0:
        raise SystemExit(
            "Run this test as your development user. PostgreSQL refuses root."
        )

    pg_bin = args.pg_bin or Path(
        subprocess.check_output(["pg_config", "--bindir"], text=True).strip()
    )
    version = subprocess.check_output(
        [pg_bin / "postgres", "--version"], text=True
    ).strip()
    if not version.startswith("postgres (PostgreSQL) 16."):
        raise SystemExit(f"Use PostgreSQL 16 as in production. Found {version}.")

    # A new run directory keeps previous receipts intact.
    directory.mkdir(mode=0o700)
    socket_dir.mkdir(mode=0o700)
    cluster = directory / "cluster"
    pg_env = {
        key: value for key, value in os.environ.items() if not key.startswith("PG")
    }
    pgctl = [pg_bin / "pg_ctl", "-D", cluster]
    socket_options = shlex.join(
        [
            "-c",
            "listen_addresses=",
            "-c",
            f"unix_socket_directories={socket_dir}",
            "-c",
            "unix_socket_permissions=0700",
            "-p",
            str(PORT),
            "-c",
            "max_connections=40",
            "-c",
            "shared_buffers=32MB",
        ]
    )
    receipt = {"started": datetime.now(UTC).isoformat(), "version": version}
    try:
        with (directory / "init.log").open("w", encoding="utf-8") as output:
            subprocess.run(
                [
                    pg_bin / "initdb",
                    "-D",
                    cluster,
                    "-U",
                    "vipi",
                    "--auth-local=trust",
                    "--auth-host=reject",
                    "--locale=C",
                    "--encoding=UTF8",
                ],
                env=pg_env,
                check=True,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        subprocess.run(
            [
                *pgctl,
                "-l",
                directory / "postgres.log",
                "-o",
                socket_options,
                "-w",
                "start",
            ],
            env=pg_env,
            check=True,
            timeout=70,
        )

        # The new cluster has no TCP listener and its socket is user-private.
        database_url = "postgresql+asyncpg://vipi@/postgres?" + urlencode(
            {"host": str(socket_dir)}
        )
        env = os.environ | {"VIPI_TEST_POSTGRES_URL": database_url}
        log = directory / "suite.log"
        with log.open("w", encoding="utf-8") as output:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "--junitxml",
                    directory / "suite.xml",
                    *args.pytest_args,
                ],
                cwd=ROOT / "backend",
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        receipt["exit_code"] = result.returncode
        print(log.read_text(encoding="utf-8"), end="")
    finally:
        try:
            if (cluster / "postmaster.pid").exists():
                subprocess.run(
                    [*pgctl, "-m", "fast", "-w", "stop"],
                    env=pg_env,
                    check=True,
                    timeout=70,
                )
            if cluster.exists():
                shutil.rmtree(cluster)
            socket_dir.rmdir()
        finally:
            receipt["finished"] = datetime.now(UTC).isoformat()
            receipt["private_cluster_removed"] = not cluster.exists()
            (directory / "result.json").write_text(
                json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
            )
    return receipt["exit_code"]


def terminated(signum, _frame):
    raise SystemExit(128 + signum)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-directory",
        type=Path,
        required=True,
        help="New disk-backed directory for logs",
    )
    parser.add_argument(
        "--pg-bin",
        type=Path,
        help="Directory with PostgreSQL 16 binaries. Defaults to pg_config.",
    )
    args, args.pytest_args = parser.parse_known_args()
    os.umask(0o077)
    signal.signal(signal.SIGTERM, terminated)
    raise SystemExit(run(args))
