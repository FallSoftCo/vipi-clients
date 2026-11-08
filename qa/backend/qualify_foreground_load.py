#!/usr/bin/env python3
"""Bounded two-process relay qualification on the owned local PostgreSQL fixture.

This measures local API/database/event handling, not internet, native crypto,
WorkOS signature verification or production-host capacity. Never target a live DB.
"""
import argparse
import asyncio
import base64
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import statistics
import subprocess
import sys
import time
from uuid import uuid4

import httpx
from sqlalchemy import text
from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from vipi.api import create_app
from vipi.auth import AuthenticationError, Principal
from vipi.config import Settings
from vipi.db import Database


def checked_url():
    url = os.environ["VIPI_TEST_POSTGRES_URL"]
    from sqlalchemy.engine import make_url
    parsed = make_url(url)
    assert parsed.host is None and parsed.database == "postgres"
    assert parsed.query.get("host") == "/home/ai/.local/state/vipi-pg-20261107"
    assert parsed.query.get("port") == "54837"
    return url


def server(schema, port):
    import uvicorn
    assert schema.startswith("vipi_load_") and schema[10:].isalnum()
    class FixtureVerifier:
        async def verify(self, token):
            if not token.startswith("load_") or not token[5:].isdigit():
                raise AuthenticationError()
            return Principal("user_" + token, "session_" + token, int(time.time()))
    url = checked_url()
    db = Database(url, connect_args={"server_settings": {"search_path": schema}})
    app = create_app(Settings(database_url=url, workos_client_id="client_loadfixture",
        workos_issuer="https://api.workos.com", service_secret="f"*43, environment="test"),
        database=db, verifier=FixtureVerifier(), store_providers={})
    uvicorn.run(app, host="127.0.0.1", port=port, ws="websockets-sansio",
        ws_max_size=512, ws_per_message_deflate=False, ws_ping_interval=20,
        ws_ping_timeout=20, limit_concurrency=500, access_log=False, log_level="warning")


def rss(process):
    try:
        for line in Path(f"/proc/{process.pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])*1024
    except FileNotFoundError:
        pass
    return 0


def distribution(values):
    values = sorted(values)
    return {"count": len(values), "median_ms": statistics.median(values)*1000,
        "p95_ms": values[min(len(values)-1, int(len(values)*.95))]*1000,
        "max_ms": max(values)*1000}


async def qualify(output, connections, rounds):
    assert 2 <= connections <= 200 and connections % 2 == 0 and 1 <= rounds <= 10
    assert not output.exists()
    output.mkdir(parents=True)
    schema = "vipi_load_" + uuid4().hex
    admin = Database(checked_url())
    async with admin.engine.begin() as c:
        await c.execute(text(f'CREATE SCHEMA "{schema}"'))
    db = Database(checked_url(), connect_args={"server_settings": {"search_path": schema}})
    await db.create_for_test(); await db.close()
    processes, logs, sockets, ports = [], [], [], []
    stop_sample = asyncio.Event()
    peaks = [0, 0]
    async def sample():
        while not stop_sample.is_set():
            for i, process in enumerate(processes): peaks[i] = max(peaks[i], rss(process))
            try: await asyncio.wait_for(stop_sample.wait(), .05)
            except TimeoutError: pass
    sampler = None
    result = {"state": "running", "schema": schema, "connections": connections,
        "rounds": rounds, "host": socket.gethostname(), "started_at": time.time(),
        "limitations": ["Local loopback; separate API processes on this workstation",
            "Fixture identity verifier; no WorkOS/JWT verification cost",
            "Opaque synthetic payload; no native encryption/translation/client UI",
            "Not a production capacity or million-user throughput claim"]}
    try:
        for i in range(2):
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0)); ports.append(s.getsockname()[1])
            log = (output / f"worker-{i}.log").open("w"); logs.append(log)
            processes.append(subprocess.Popen([sys.executable, __file__, "--serve", schema,
                "--port", str(ports[-1])], stdout=log, stderr=subprocess.STDOUT))
        sampler = asyncio.create_task(sample())
        async with httpx.AsyncClient(timeout=15, limits=httpx.Limits(max_connections=40)) as client:
            for port in ports:
                async with asyncio.timeout(15):
                    while True:
                        try:
                            if (await client.get(f"http://127.0.0.1:{port}/health/ready")).status_code == 200: break
                        except httpx.ConnectError: pass
                        await asyncio.sleep(.1)
            semaphore = asyncio.Semaphore(20)
            async def setup(i):
                async with semaphore:
                    base = f"http://127.0.0.1:{ports[i%2]}"
                    headers = {"Authorization": "Bearer load_"+str(i)}
                    response = await client.put(base+"/v1/me", headers=headers,
                        json={"username": f"load_{i:04}", "display_name": "Load fixture"})
                    assert response.status_code == 200, response.status_code
                    user = response.json()["id"]
                    device = str(uuid4()); secret = secrets.token_urlsafe(32)
                    response = await client.post(base+"/v1/devices", headers=headers,
                        json={"device_id": device, "secret": secret})
                    assert response.status_code == 200, response.status_code
                    headers |= {"X-Vipi-Device-ID": device, "X-Vipi-Device-Secret": secret}
                    ws = await connect(base.replace("http:","ws:")+"/v1/events",
                        additional_headers=headers, ping_interval=None, proxy=None)
                    sockets.append(ws)
                    assert await asyncio.wait_for(ws.recv(), 10) == '{"event":"inbox_changed"}'
                    return base, headers, user, device, ws
            accounts = await asyncio.gather(*(setup(i) for i in range(connections)))
            accepts, arrivals, receipts = [], [], []
            start = time.monotonic()
            async def conversation(a, b):
                for _ in range(rounds):
                    async with semaphore:
                        message = {"id": str(uuid4()), "recipient_id": b[2], "recipient_device_id": b[3],
                            "created_at": datetime.now(UTC).isoformat(), "cipher_type": 3,
                            "ciphertext": base64.b64encode(b"Opaque synthetic load fixture. "*8).decode()}
                        began = time.monotonic()
                        response = await client.post(a[0]+"/v1/messages", headers=a[1], json=message)
                        assert response.status_code == 200 and response.json()["state"] == "accepted"
                        accepts.append(time.monotonic()-began)
                        assert await asyncio.wait_for(b[4].recv(), 10) == '{"event":"inbox_changed"}'
                        arrivals.append(time.monotonic()-began)
                        response = await client.get(b[0]+"/v1/messages/pending", headers=b[1])
                        assert response.status_code == 200
                        assert [m["id"] for m in response.json()["messages"]] == [message["id"]]
                        began = time.monotonic()
                        response = await client.post(b[0]+"/v1/messages/"+message["id"]+"/receipt", headers=b[1])
                        assert response.status_code == 200 and response.json()["state"] == "delivered"
                        assert await asyncio.wait_for(a[4].recv(), 10) == '{"event":"inbox_changed"}'
                        receipts.append(time.monotonic()-began)
                        a, b = b, a
            await asyncio.gather(*(conversation(accounts[i], accounts[i+1]) for i in range(0, connections, 2)))
            elapsed = time.monotonic()-start
            async with admin.engine.begin() as c:
                row = (await c.execute(text(f'SELECT count(*), count(ciphertext), count(*) FILTER (WHERE state=\'delivered\') FROM "{schema}".pending_messages'))).one()
            assert row == (connections//2*rounds, 0, connections//2*rounds)
            result.update(state="passed", measured_exchange_seconds=elapsed,
                complete_message_and_receipt_exchanges=row[0], exchanges_per_second=row[0]/elapsed,
                accept=distribution(accepts), recipient_hint=distribution(arrivals), sender_receipt_hint=distribution(receipts),
                api_process_peak_rss_bytes=peaks, ciphertext_rows_remaining=0)
    except BaseException as error:
        result.update(state="failed", failure_type=type(error).__name__)
        raise
    finally:
        await asyncio.gather(*(s.close() for s in sockets), return_exceptions=True)
        stop_sample.set()
        if sampler: await sampler
        for p in processes:
            if p.poll() is None: p.send_signal(signal.SIGINT)
        for p in processes:
            try: p.wait(timeout=8)
            except subprocess.TimeoutExpired: p.kill(); p.wait(timeout=5)
        for f in logs: f.close()
        async with admin.engine.begin() as c:
            await c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.close()
        result.update(finished_at=time.time(), schema_removed=True, workers_stopped=True)
        (output/"receipt.json").write_text(json.dumps(result, indent=2)+"\n")
        print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve"); parser.add_argument("--port", type=int)
    parser.add_argument("--output", type=Path); parser.add_argument("--connections", type=int, default=192)
    parser.add_argument("--rounds", type=int, default=5)
    args = parser.parse_args()
    if args.serve: server(args.serve, args.port)
    else:
        assert args.output is not None
        asyncio.run(qualify(args.output, args.connections, args.rounds))
