#!/usr/bin/env python3
"""Private iPad QA through an explicitly forwarded usbmux socket.

Requires pymobiledevice3; never installed in the app or used for customer data.
Start with list. Press only an exact, freshly observed accessibility caption.
"""

import argparse
import asyncio
import json

from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit


def serializable(value):
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if hasattr(value, "_fields"):
        return {"type": type(value).__name__, "fields": value._fields}
    return str(value)


def unwrap(value):
    if isinstance(value, list):
        return [unwrap(item) for item in value]
    if isinstance(value, dict):
        if "ObjectType" in value:
            return unwrap(value.get("Value"))
        return {key: unwrap(item) for key, item in value.items()}
    return value


def wire_fields(value):
    while isinstance(value, dict) and "ObjectType" in value:
        value = value["Value"]
    return value


def activation(value):
    if isinstance(value, dict):
        if value.get("ObjectType") == "AXAuditElementAttribute_v1":
            fields = unwrap(value)
            if fields.get("AttributeNameValue_v1") == "AXAction-2010":
                return value
        for item in value.values():
            found = activation(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = activation(item)
            if found:
                return found
    return None


async def main(args):
    async with UserspaceRsdTunnel(serial=args.udid) as rsd:
        async with AccessibilityAudit(rsd) as service:
            await service.set_app_monitoring_enabled(True)
            await service.set_monitored_event_type()
            await service.move_focus_next()
            visited = set()
            previous = None
            for _ in range(100):
                name, values = await asyncio.wait_for(service._event_queue.get(), 5)
                if name != "hostInspectorCurrentElementChanged:":
                    continue
                raw = values[0]
                fields = unwrap(raw)
                caption = fields.get("CaptionTextValue_v1")
                element = fields.get("ElementValue_v1", {})
                key = element.get("PlatformElementValue_v1")
                matched = (
                    args.find is None or args.find.casefold() in str(caption).casefold()
                )
                if matched:
                    print(
                        json.dumps(
                            {"caption": caption, "element": element},
                            default=serializable,
                        ),
                        flush=True,
                    )
                    if args.find is not None:
                        return
                if key is None:
                    await service.move_focus_next()
                    continue
                if key in visited:
                    break
                visited.add(key)
                if args.press == caption and (
                    args.after is None or args.after == previous
                ):
                    action = activation(raw)
                    if action is None:
                        raise RuntimeError("Observed element has no activation action")
                    # Reuse the device's exact wire schema. pymobiledevice3's
                    # current helper constructs a malformed nested Value field.
                    await service._invoke(
                        "deviceElement:performAction:withValue:",
                        wire_fields(raw)["ElementValue_v1"],
                        action,
                        0,
                        expects_reply=False,
                    )
                    await asyncio.sleep(2)
                    print(
                        json.dumps({"activation_sent": caption, "after": previous}),
                        flush=True,
                    )
                    return
                previous = caption
                await service.move_focus_next()
            if args.press or args.find:
                raise RuntimeError("Requested caption/context was not found")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--udid", required=True)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--press")
    actions.add_argument(
        "--find", help="Read-only caption substring lookup; never activates an element"
    )
    parser.add_argument("--after")
    asyncio.run(main(parser.parse_args()))
