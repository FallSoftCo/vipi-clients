#!/usr/bin/env python3
"""Small same-origin Vipi launch-list service.

The public marketing site is static. This service owns only the waitlist row
and does not share the Vipi app API, database, keys, or process lifecycle.
"""

from __future__ import annotations

import json
import os
import re
import signal
import sqlite3
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


MAX_BODY = 4096
MAX_EMAIL = 254
MAX_TEXT = 180
MAX_PATH = 300
MAX_REFERRER = 1000
RATE_LIMIT = 8
RATE_WINDOW_SECONDS = 600
ALLOWED_ORIGIN = "https://mambovipi.app"
CONSENT_VERSION = "launch-waitlist-2026-11-22"
EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")
UTM_FIELDS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_email(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("email_required")
    email = value.strip().lower()
    if not email or len(email) > MAX_EMAIL or not EMAIL_RE.fullmatch(email):
        raise ValueError("email_invalid")
    local, domain = email.rsplit("@", 1)
    if not local or not domain or ".." in email:
        raise ValueError("email_invalid")
    return email


def clean_text(value: Any, limit: int = MAX_TEXT) -> str:
    if not isinstance(value, str):
        return ""
    value = CONTROL_RE.sub("", value).strip()
    return value[:limit]


def clean_path(value: Any) -> str:
    value = clean_text(value, MAX_PATH)
    if not value:
        return ""
    path = urlparse(value).path if "://" in value else value.split("?", 1)[0]
    return path[:MAX_PATH] if path.startswith("/") else ""


def clean_referrer(value: Any) -> str:
    value = clean_text(value, MAX_REFERRER)
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return ""
    # Do not retain query strings or fragments from an outside referrer.
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"[:MAX_REFERRER]


class WaitlistStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS waitlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    first_utm_source TEXT NOT NULL DEFAULT '',
                    first_utm_medium TEXT NOT NULL DEFAULT '',
                    first_utm_campaign TEXT NOT NULL DEFAULT '',
                    first_utm_content TEXT NOT NULL DEFAULT '',
                    first_utm_term TEXT NOT NULL DEFAULT '',
                    first_landing_path TEXT NOT NULL DEFAULT '',
                    first_referrer TEXT NOT NULL DEFAULT '',
                    first_created_at TEXT NOT NULL,
                    last_utm_source TEXT NOT NULL DEFAULT '',
                    last_utm_medium TEXT NOT NULL DEFAULT '',
                    last_utm_campaign TEXT NOT NULL DEFAULT '',
                    last_utm_content TEXT NOT NULL DEFAULT '',
                    last_utm_term TEXT NOT NULL DEFAULT '',
                    last_landing_path TEXT NOT NULL DEFAULT '',
                    last_referrer TEXT NOT NULL DEFAULT '',
                    last_submitted_at TEXT NOT NULL,
                    consent_at TEXT NOT NULL,
                    consent_version TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS waitlist_campaign_idx ON waitlist(first_utm_campaign, first_utm_content)")

    def add(self, record: dict[str, str]) -> bool:
        now = utc_now()
        with self.connect() as conn:
            inserted = conn.execute(
                """
                INSERT OR IGNORE INTO waitlist (
                    email,
                    first_utm_source, first_utm_medium, first_utm_campaign, first_utm_content, first_utm_term,
                    first_landing_path, first_referrer, first_created_at,
                    last_utm_source, last_utm_medium, last_utm_campaign, last_utm_content, last_utm_term,
                    last_landing_path, last_referrer, last_submitted_at, consent_at, consent_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["email"],
                    record.get("utm_source", ""), record.get("utm_medium", ""), record.get("utm_campaign", ""),
                    record.get("utm_content", ""), record.get("utm_term", ""),
                    record.get("landing_path", ""), record.get("referrer", ""), now,
                    record.get("utm_source", ""), record.get("utm_medium", ""), record.get("utm_campaign", ""),
                    record.get("utm_content", ""), record.get("utm_term", ""),
                    record.get("landing_path", ""), record.get("referrer", ""), now, now, CONSENT_VERSION,
                ),
            )
            if inserted.rowcount == 1:
                return True
            conn.execute(
                """
                UPDATE waitlist SET
                    last_utm_source=?, last_utm_medium=?, last_utm_campaign=?, last_utm_content=?, last_utm_term=?,
                    last_landing_path=?, last_referrer=?, last_submitted_at=?, consent_at=?, consent_version=?
                WHERE email=?
                """,
                (
                    record.get("utm_source", ""), record.get("utm_medium", ""), record.get("utm_campaign", ""),
                    record.get("utm_content", ""), record.get("utm_term", ""),
                    record.get("landing_path", ""), record.get("referrer", ""), now, now, CONSENT_VERSION,
                    record["email"],
                ),
            )
            return False

    def healthy(self) -> bool:
        with self.connect() as conn:
            return conn.execute("SELECT 1").fetchone()[0] == 1


class RateLimiter:
    def __init__(self, limit: int = RATE_LIMIT, window: int = RATE_WINDOW_SECONDS):
        self.limit = limit
        self.window = window
        self.lock = threading.Lock()
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            bucket = self.hits[key]
            while bucket and now - bucket[0] > self.window:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True

    def clear(self) -> None:
        with self.lock:
            self.hits.clear()


class WaitlistServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], store: WaitlistStore, *, origin: str = ALLOWED_ORIGIN):
        super().__init__(address, WaitlistHandler)
        self.store = store
        self.origin = origin
        self.limiter = RateLimiter()


class WaitlistHandler(BaseHTTPRequestHandler):
    server: WaitlistServer
    server_version = "VipiWaitlist/1"
    sys_version = ""

    def log_message(self, fmt: str, *args: Any) -> None:
        # Never log request bodies or email addresses.
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, code: str, message: str) -> None:
        self._send(status, {"ok": False, "code": code, "message": message})

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            try:
                self._send(200, {"ok": True, "database": self.server.store.healthy()})
            except Exception:
                self._error(503, "unavailable", "Service unavailable.")
            return
        self._error(405, "method", "Method not allowed.")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/waitlist":
            self._error(404, "not_found", "Not found.")
            return

        origin = self.headers.get("Origin")
        if origin and origin != self.server.origin:
            self._error(403, "origin", "Request not accepted.")
            return
        if not self.server.limiter.allow(self.client_address[0]):
            self._error(429, "rate_limit", "Too many tries. Please wait a moment.")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            self._error(413, "size", "Request is too large.")
            return
        if self.headers.get_content_type() != "application/json":
            self._error(415, "content_type", "JSON required.")
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error(400, "json", "Invalid request.")
            return
        if not isinstance(payload, dict):
            self._error(400, "json", "Invalid request.")
            return
        if clean_text(payload.get("company_url"), 200):
            self._send(201, {"ok": True, "duplicate": False, "message": "You’re on the list."})
            return
        if payload.get("consent") is not True:
            self._error(400, "consent", "Please agree to receive launch news.")
            return

        try:
            email = normalize_email(payload.get("email"))
        except ValueError as exc:
            self._error(400, str(exc), "Enter a valid email address.")
            return

        record = {"email": email}
        for field in UTM_FIELDS:
            record[field] = clean_text(payload.get(field), MAX_TEXT)
        record["landing_path"] = clean_path(payload.get("landing_path"))
        record["referrer"] = clean_referrer(payload.get("referrer"))

        try:
            inserted = self.server.store.add(record)
        except sqlite3.Error:
            self._error(503, "database", "Could not save your email. Please try again.")
            return
        self._send(201 if inserted else 200, {
            "ok": True,
            "duplicate": not inserted,
            "message": "You’re on the list. We’ll email you when Vipi opens.",
        })


def make_server(db_path: str | Path, host: str = "127.0.0.1", port: int = 9876) -> WaitlistServer:
    return WaitlistServer((host, port), WaitlistStore(db_path))


def main() -> None:
    db_path = os.environ.get("VIPI_WAITLIST_DB", "/var/lib/vipi-waitlist/waitlist.sqlite3")
    host = os.environ.get("VIPI_WAITLIST_HOST", "127.0.0.1")
    port = int(os.environ.get("VIPI_WAITLIST_PORT", "9876"))
    server = make_server(db_path, host, port)

    def stop(_signum: int, _frame: Any) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(f"vipi-waitlist listening on {host}:{port}; db={db_path}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
