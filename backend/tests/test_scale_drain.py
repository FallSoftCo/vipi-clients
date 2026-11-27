"""Two independent API instances and one private Nginx master on a fresh PG16 fixture."""

import asyncio
from contextlib import AsyncExitStack, ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import httpx
import pytest
from sqlalchemy import text
from websockets.asyncio.client import connect

from test_media import envelope, identity, seal


def listen():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(32)
    return sock


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def spawn(stack, args, log, **kwargs):
    with log.open("ab") as output:
        process = subprocess.Popen(
            args, stdout=output, stderr=subprocess.STDOUT, **kwargs
        )
    stack.callback(stop, process)
    return process


def proxy_config(front, first, second, draining):
    # The QA-only header selects an origin for a particular operation. Ordinary
    # requests use round robin. After reload even the old selection goes to B.
    members = [second] if draining else [first, second]
    servers = "\n".join(f"server 127.0.0.1:{port};" for port in members)
    return f"""
worker_processes 1;
pid nginx.pid;
error_log error.log notice;
events {{ worker_connections 128; }}
http {{
    access_log off;
    client_body_temp_path body;
    proxy_temp_path proxy;
    fastcgi_temp_path fastcgi;
    uwsgi_temp_path uwsgi;
    scgi_temp_path scgi;
    upstream balanced {{ {servers} }}
    upstream node_a {{ server 127.0.0.1:{second if draining else first}; }}
    upstream node_b {{ server 127.0.0.1:{second}; }}
    map $http_x_fixture_origin $pool {{ default balanced; a node_a; b node_b; }}
    map $http_upgrade $connection_upgrade {{ default upgrade; '' close; }}
    server {{
        listen 127.0.0.1:{front};
        location / {{
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $connection_upgrade;
            proxy_request_buffering off;
            proxy_buffering off;
            proxy_next_upstream off;
            proxy_pass http://$pool;
            add_header X-Fixture-Upstream $upstream_addr always;
        }}
    }}
}}
"""


async def until(check):
    async with asyncio.timeout(10):
        while not await check():
            await asyncio.sleep(0.025)


async def qualify_pool_limits(db, clients, headers):
    # A bounded, reversible queue inside this run's throwaway schema. The two
    # surplus requests at each origin must complete after the lock is released.
    waiters = {}

    async def saturated():
        async with db.engine.connect() as observer:
            rows = await observer.execute(
                text("""
                SELECT application_name, count(*)
                FROM pg_stat_activity
                WHERE datname=current_database() AND wait_event_type='Lock'
                  AND application_name IN ('scale-fixture-a','scale-fixture-b')
                GROUP BY application_name
            """)
            )
            waiters.clear()
            waiters.update(rows.all())
            return waiters == {"scale-fixture-a": 15, "scale-fixture-b": 15}

    tasks = []
    try:
        async with db.engine.begin() as lock:
            await lock.execute(text("LOCK TABLE rate_windows IN ACCESS EXCLUSIVE MODE"))
            tasks = [
                asyncio.create_task(c.get("/v1/messages/pending", headers=headers))
                for c in clients
                for _ in range(17)
            ]
            await until(saturated)
            assert all(not t.done() for t in tasks)
        results = await asyncio.gather(*tasks)
        assert all(r.status_code == 200 and r.json()["messages"] == [] for r in results)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return waiters


def listener_inode(port):
    for line in Path("/proc/net/tcp").read_text().splitlines()[1:]:
        fields = line.split()
        if fields[1] == f"0100007F:{port:04X}" and fields[3] == "0A":
            return f"socket:[{fields[9]}]"
    raise AssertionError("fixture frontend listener missing")


def holds_fd(pid, target):
    for fd in Path(f"/proc/{pid}/fd").iterdir():
        try:
            if str(fd.readlink()) == target:
                return True
        except FileNotFoundError:
            continue
    return False


def origin(response):
    return int(response.headers["x-fixture-upstream"].rsplit(":", 1)[1])


async def hint(ws):
    assert json.loads(await asyncio.wait_for(ws.recv(), 5)) == {
        "event": "inbox_changed"
    }


@pytest.mark.skipif(
    not os.environ.get("SCALE_NGINX"),
    reason="opt in using the private PG/Nginx runbook",
)
async def test_scale_drain(db, tmp_path):
    nginx = shutil.which(os.environ["SCALE_NGINX"])
    assert nginx, "Set SCALE_NGINX to the Nginx executable"
    assert db.engine.dialect.name == "postgresql"
    tests = Path(__file__).resolve().parent
    storage = tmp_path / "media"
    with ExitStack() as processes:
        async with db.sessions() as session:
            schema = await session.scalar(text("SELECT current_schema()"))
            assert schema.startswith("vipi_test_")
        workers, ports = [], []
        for label in ("a", "b"):
            with listen() as sock:
                ports.append(sock.getsockname()[1])
                spec = dict(
                    database_url=db.engine.url.render_as_string(hide_password=False),
                    schema=schema,
                    storage=str(storage),
                    fd=sock.fileno(),
                    application_name="scale-fixture-" + label,
                    crash_after_finalize=False,
                )
                env = {k: v for k, v in os.environ.items() if not k.startswith("VIPI_")}
                env["PYTHONPATH"] = str(tests.parent)
                workers.append(
                    spawn(
                        processes,
                        [
                            sys.executable,
                            str(tests / "media_worker.py"),
                            json.dumps(spec),
                        ],
                        tmp_path / f"{label}.log",
                        pass_fds=(sock.fileno(),),
                        env=env,
                    )
                )
        with listen() as probe:
            front = probe.getsockname()[1]
        first, second = ports
        config = tmp_path / "nginx.conf"
        (tmp_path / "logs").mkdir()
        config.write_text(proxy_config(front, first, second, False))
        cmd = [nginx, "-p", str(tmp_path), "-c", str(config)]
        master = spawn(processes, [*cmd, "-g", "daemon off;"], tmp_path / "master.log")
        # Fresh connections make proxy-generation observations unambiguous.
        base = f"http://127.0.0.1:{front}"
        async with AsyncExitStack() as clients:

            async def client(label=None):
                return await clients.enter_async_context(
                    httpx.AsyncClient(
                        base_url=base,
                        trust_env=False,
                        timeout=15,
                        limits=httpx.Limits(max_keepalive_connections=0),
                        headers={"X-Fixture-Origin": label} if label else {},
                    )
                )

            a, b, normal = await client("a"), await client("b"), await client()

            async def ready():
                assert all(p.poll() is None for p in [master, *workers])
                try:
                    for c, port in zip((a, b), ports):
                        r = await c.get("/health/ready")
                        if r.status_code != 200 or origin(r) != port:
                            return False
                    return True
                except httpx.ConnectError:
                    return False

            await until(ready)
            assert {origin(await normal.get("/health/ready")) for _ in range(4)} == set(
                ports
            )
            _, _, sender = await identity(a, "alice")
            bob, device, recipient = await identity(b, "bob")
            assert (await a.get("/v1/entitlements", headers=sender)).status_code == 200

            async def events(label, headers, port):
                ws = await clients.enter_async_context(
                    connect(
                        base.replace("http:", "ws:") + "/v1/events",
                        additional_headers=headers | {"X-Fixture-Origin": label},
                        proxy=None,
                    )
                )
                assert origin(ws.response) == port
                await hint(ws)
                return ws

            pool_waiters = await qualify_pool_limits(db, (a, b), recipient)
            old_socket = await events("a", sender, first)
            recipient_socket = await events("a", recipient, first)
            direct = envelope(bob, device, [])
            admitted = await a.post("/v1/messages", headers=sender, json=direct)
            assert origin(admitted) == first and admitted.json()["state"] == "accepted"
            await hint(recipient_socket)
            await recipient_socket.close()
            clear = os.urandom(192 * 1024)
            key = AESGCM.generate_key(bit_length=256)
            attachment, blob = str(uuid4()), str(uuid4())
            cipher = seal(clear, key, attachment, "original")
            meta = dict(
                id=blob,
                ciphertext_bytes=len(cipher),
                ciphertext_sha256=hashlib.sha256(cipher).hexdigest(),
            )
            path = f"/v1/media/{blob}/ciphertext"
            assert (
                await a.post("/v1/media/uploads", headers=sender, json=meta)
            ).json()["state"] == "uploading"
            release = asyncio.Event()

            async def body():
                yield cipher[:65536]
                await asyncio.wait_for(release.wait(), 15)
                yield cipher[65536:]

            upload = asyncio.create_task(
                a.put(
                    path,
                    headers=sender | {"Content-Length": str(len(cipher))},
                    content=body(),
                )
            )

            async def written():
                for part in storage.glob(f"{blob}.*.part"):
                    with part.open("rb") as stream:
                        if stream.read(32768) == cipher[:32768]:
                            return True
                return False

            try:
                await until(written)
                children = Path(f"/proc/{master.pid}/task/{master.pid}/children")
                old_workers = set(children.read_text().split())
                assert len(old_workers) == 1
                old_worker = next(iter(old_workers))
                listening = listener_inode(front)
                assert holds_fd(old_worker, listening)
                config.write_text(proxy_config(front, first, second, True))
                subprocess.run([*cmd, "-t"], check=True, capture_output=True, timeout=5)
                master.send_signal(signal.SIGHUP)

                async def switched():
                    if holds_fd(old_worker, listening):
                        return False
                    r = await a.get("/health/ready")
                    return r.status_code == 200 and origin(r) == second

                await until(switched)
                assert old_workers <= set(children.read_text().split())
                assert {
                    origin(await normal.get("/health/ready")) for _ in range(4)
                } == {second}
                retry = await a.post("/v1/messages", headers=sender, json=direct)
                assert origin(retry) == second and retry.json() == admitted.json()
            finally:
                release.set()
                finished = await upload
            assert origin(finished) == first and finished.json()["state"] == "ready"
            await events("a", recipient, second)
            pending = (await b.get("/v1/messages/pending", headers=recipient)).json()[
                "messages"
            ]
            assert [(m["id"], m["ciphertext"]) for m in pending] == [
                (direct["id"], direct["ciphertext"])
            ]
            receipt = f"/v1/messages/{direct['id']}/receipt"
            for _ in range(2):
                assert (await b.post(receipt, headers=recipient)).json()[
                    "state"
                ] == "delivered"
            await hint(old_socket)
            await old_socket.close()

            async def retired():
                return not (old_workers & set(children.read_text().split()))

            await until(retired)
            workers[0].terminate()
            assert await asyncio.to_thread(workers[0].wait, 8) in (0, -signal.SIGTERM)
            assert (await b.get(path, headers=recipient)).status_code == 404
            with_media = envelope(bob, device, [blob])
            accepted = await normal.post(
                "/v1/messages", headers=sender, json=with_media
            )
            assert origin(accepted) == second and accepted.json()["state"] == "accepted"
            download = await b.get(path, headers=recipient)
            assert origin(download) == second and download.content == cipher
            aad = f"vipi-attachment-v1\0{attachment}\0original".encode()
            assert AESGCM(key).decrypt(cipher[:12], download.content[12:], aad) == clear
            assert (
                await normal.post(
                    f"/v1/messages/{with_media['id']}/receipt", headers=recipient
                )
            ).json()["state"] == "delivered"
            assert (await normal.get("/v1/messages/pending", headers=recipient)).json()[
                "messages"
            ] == []
            assert len(list(storage.glob("*.ciphertext"))) == 1 and not list(
                storage.glob("*.part")
            )
            async with db.sessions() as session:
                counts = (
                    await session.execute(
                        text("""
                    SELECT (SELECT count(*) FROM pending_messages),
                           (SELECT count(*) FROM pending_messages WHERE state='delivered' AND ciphertext IS NULL),
                           (SELECT count(*) FROM media_blobs WHERE state='ready' AND upload_token IS NULL),
                           (SELECT count(*) FROM media_grants),
                           (SELECT generation FROM push_outbox WHERE device_id=:device)
                """),
                        {"device": device},
                    )
                ).one()
            assert tuple(counts) == (2, 2, 1, 1, 2), (
                "each new send must enqueue exactly one hint generation"
            )

            evidence = {
                "api_processes": [p.pid for p in workers],
                "nginx_master": master.pid,
                "nginx_original_worker": int(old_worker),
                "ordinary_upstreams_before": list(ports),
                "ordinary_upstreams_after": [second],
                "original_listener_released": True,
                "original_socket_received_receipt_hint_after_reload": True,
                "held_upload_ciphertext_bytes": len(cipher),
                "original_upload_completed_on": origin(finished),
                "authorized_download_after_retirement_on": origin(download),
                "original_worker_exited_before_node_a_stop": True,
                "recipient_socket_before_and_after_reconnect": [first, second],
                "pg_blocked_orm_sessions_at_saturation": pool_waiters,
                "pg_requests_offered_per_origin": 17,
                "delivered_messages": counts[1],
                "ready_blobs": counts[2],
                "attachment_grants": counts[3],
                "push_outbox_generation": counts[4],
            }
            (tmp_path / "scale-drain.json").write_text(
                json.dumps(evidence, indent=2) + "\n"
            )
