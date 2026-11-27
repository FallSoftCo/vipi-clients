#!/usr/bin/env python3
"""Retain raw physical-device audit details that XCTest sometimes omits.

Private QA tooling only; no system accessibility setting is changed.
The caller supplies an explicitly forwarded paired-device usbmux socket.
"""

import argparse
import asyncio
import json
from pathlib import Path
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.services.dvt.instruments.screenshot import Screenshot
from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit


def serialize(value):
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if hasattr(value, "_fields"):
        return {"type": type(value).__name__, "fields": value._fields}
    raise TypeError(type(value).__name__)


async def main(udid, capture):
    async with UserspaceRsdTunnel(serial=udid) as rsd:
        if capture:
            if capture.exists():
                raise FileExistsError(capture)
            async with DvtProvider(rsd) as provider:
                async with Screenshot(provider) as screenshot:
                    capture.write_bytes(await screenshot.get_screenshot())
        async with AccessibilityAudit(rsd) as service:
            await service.set_app_monitoring_enabled(True)
            supported = await service.supported_audits_types()
            print(json.dumps({"supported": supported}, default=serialize), flush=True)
            issues = await asyncio.wait_for(service.run_audit(supported), 60)
            print(json.dumps({"issues": issues}, default=serialize), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--udid", required=True)
    parser.add_argument("--capture", type=Path)
    args = parser.parse_args()
    asyncio.run(asyncio.wait_for(main(args.udid, args.capture), 120))
