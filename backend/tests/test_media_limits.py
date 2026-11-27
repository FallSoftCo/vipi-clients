"""Network backpressure must not hold an opaque-file descriptor indefinitely."""

import asyncio
from uuid import uuid4
import pytest
from vipi.media import MediaTransferLimits


def scope(method="GET", path=None):
    return {
        "type": "http",
        "method": method,
        "path": path or f"/v1/media/{uuid4()}/ciphertext",
    }


async def test_blocked_response_send_is_cancelled_and_stream_cleanup_runs():
    entered = asyncio.Event()
    closed = asyncio.Event()
    events = []

    async def app(scope, receive, send):
        try:
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send(
                {"type": "http.response.body", "body": b"opaque", "more_body": True}
            )
        finally:
            closed.set()

    async def blocked(event):
        events.append(event)
        if event["type"] == "http.response.body":
            entered.set()
            await asyncio.Event().wait()

    limiter = MediaTransferLimits(app, seconds=0.05, connections=1)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(limiter(scope(), None, blocked), 1)
    assert entered.is_set() and closed.is_set() and limiter.active == 0
    assert not any(e.get("more_body") is False for e in events)


async def test_busy_stream_is_bounded_but_ordinary_routes_remain_available():
    entered = asyncio.Event()
    release = asyncio.Event()
    ordinary = []
    rejected = []

    async def app(scope, receive, send):
        if scope["path"] == "/health/live":
            ordinary.append(True)
            return
        entered.set()
        await release.wait()

    async def capture(event):
        rejected.append(event)

    limiter = MediaTransferLimits(app, seconds=1, connections=1)
    task = asyncio.create_task(limiter(scope("PUT"), None, capture))
    await asyncio.wait_for(entered.wait(), 1)
    try:
        await limiter(scope(), None, capture)
        assert rejected[0]["status"] == 429 and b"media_busy" in rejected[1]["body"]
        await limiter(scope(path="/health/live"), None, capture)
        assert ordinary == [True]
    finally:
        release.set()
        await task
    assert limiter.active == 0


async def test_timeout_before_response_returns_explicit_retryable_error():
    cleanup = asyncio.Event()
    events = []

    async def app(*_):
        try:
            await asyncio.Event().wait()
        finally:
            cleanup.set()

    async def send(event):
        events.append(event)

    limiter = MediaTransferLimits(app, seconds=0.05, connections=1)
    await limiter(scope("PUT"), None, send)
    assert cleanup.is_set() and limiter.active == 0
    assert events[0]["status"] == 408 and b"media_transfer_timeout" in events[1]["body"]


async def test_actual_file_descriptor_closes_when_headers_block_before_iteration(
    tmp_path,
):
    from vipi.media import CiphertextResponse

    path = tmp_path / "opaque.ciphertext"
    path.write_bytes(b"opaque test bytes")
    stream = path.open("rb")
    response = CiphertextResponse(
        stream, headers={"Content-Length": str(path.stat().st_size)}
    )

    async def app(scope, receive, send):
        await response(scope, receive, send)

    async def blocked(_):
        await asyncio.Event().wait()

    limiter = MediaTransferLimits(app, seconds=0.05, connections=1)
    request = scope()
    request["asgi"] = {"spec_version": "2.4"}
    with pytest.raises(TimeoutError):
        await limiter(request, None, blocked)
    assert stream.closed and limiter.active == 0


@pytest.mark.parametrize(
    "ident", [str(uuid4()).upper(), uuid4().hex, "{" + str(uuid4()) + "}"]
)
async def test_alternate_uuid_spellings_cannot_bypass_transfer_admission(ident):
    called = False
    events = []

    async def app(*_):
        nonlocal called
        called = True

    async def send(event):
        events.append(event)

    limiter = MediaTransferLimits(app, seconds=1, connections=1)
    limiter.active = 1
    await limiter(scope(path="/v1/media/" + ident + "/ciphertext"), None, send)
    assert not called and events[0]["status"] == 429
