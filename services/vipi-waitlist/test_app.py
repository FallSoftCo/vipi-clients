#!/usr/bin/env python3
from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from app import WaitlistStore, clean_path, clean_referrer, make_server, normalize_email


class WaitlistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "waitlist.sqlite3"
        self.store = WaitlistStore(self.db)
        self.server = make_server(self.db, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def post(self, payload: dict, *, origin: str = "https://mambovipi.app") -> tuple[int, dict]:
        body = json.dumps(payload)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("POST", "/api/waitlist", body=body, headers={
            "Content-Type": "application/json",
            "Origin": origin,
        })
        response = conn.getresponse()
        data = json.loads(response.read())
        conn.close()
        return response.status, data

    def valid(self, **changes):
        payload = {
            "email": "reader@example.com",
            "consent": True,
            "utm_source": "instagram",
            "utm_medium": "social",
            "utm_campaign": "vipi_depth_launch",
            "utm_content": "post-01-es-keys",
            "utm_term": "native_shallow_deep",
            "landing_path": "/?utm_source=instagram",
            "referrer": "https://l.instagram.com/?u=private",
            "company_url": "",
        }
        payload.update(changes)
        return payload

    def test_email_normalization(self):
        self.assertEqual(normalize_email(" Reader@Example.COM "), "reader@example.com")
        for value in ("", "no-at", "a@b", "a@@b.com", "a..b@example.com"):
            with self.assertRaises(ValueError):
                normalize_email(value)

    def test_attribution_cleanup(self):
        self.assertEqual(clean_path("/links.html?utm_source=instagram"), "/links.html")
        self.assertEqual(clean_path("https://mambovipi.app/?utm_source=instagram"), "/")
        self.assertEqual(clean_referrer("https://l.instagram.com/?u=secret#x"), "https://l.instagram.com/")
        self.assertEqual(clean_referrer("javascript:alert(1)"), "")

    def test_insert_preserves_first_touch(self):
        self.assertTrue(self.store.add({"email": "reader@example.com", "utm_content": "first", "utm_source": "instagram"}))
        self.assertFalse(self.store.add({"email": "reader@example.com", "utm_content": "last", "utm_source": "instagram"}))
        with self.store.connect() as conn:
            row = conn.execute("SELECT * FROM waitlist WHERE email=?", ("reader@example.com",)).fetchone()
        self.assertEqual(row["first_utm_content"], "first")
        self.assertEqual(row["last_utm_content"], "last")

    def test_http_success_and_duplicate(self):
        status, body = self.post(self.valid())
        self.assertEqual(status, 201)
        self.assertTrue(body["ok"])
        self.assertFalse(body["duplicate"])
        status, body = self.post(self.valid(utm_content="post-02"))
        self.assertEqual(status, 200)
        self.assertTrue(body["duplicate"])

    def test_consent_required(self):
        status, body = self.post(self.valid(consent=False))
        self.assertEqual(status, 400)
        self.assertEqual(body["code"], "consent")

    def test_origin_rejected(self):
        status, body = self.post(self.valid(), origin="https://evil.example")
        self.assertEqual(status, 403)
        self.assertEqual(body["code"], "origin")

    def test_honeypot_returns_success_without_row(self):
        status, body = self.post(self.valid(company_url="https://spam.example"))
        self.assertEqual(status, 201)
        self.assertTrue(body["ok"])
        with self.store.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM waitlist").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
