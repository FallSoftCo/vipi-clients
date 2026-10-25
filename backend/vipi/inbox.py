"""Device-bound keyset cursors survive receipts removing earlier queue items."""
import base64
import binascii
import hashlib
import hmac
import json
from datetime import datetime
from uuid import UUID

from .delivery import DeliveryError, utc


def encode_cursor(device_id: str, accepted_at: datetime, message_id: str, secret: str) -> str:
    data = json.dumps([1, device_id, utc(accepted_at).isoformat(), message_id], separators=(',', ':')).encode()
    signature = hmac.digest(secret.encode(), b'vipi-inbox-v1\0' + data, hashlib.sha256)
    return base64.urlsafe_b64encode(data + signature).decode().rstrip('=')


def decode_cursor(value: str, device_id: str, secret: str) -> tuple[datetime, str]:
    try:
        if not value or len(value) > 512:
            raise ValueError()
        raw = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
        data, signature = raw[:-32], raw[-32:]
        if not hmac.compare_digest(signature, hmac.digest(secret.encode(), b'vipi-inbox-v1\0' + data, hashlib.sha256)):
            raise ValueError()
        version, device, accepted, message_id = json.loads(data)
        if version != 1 or device != device_id:
            raise ValueError()
        instant = datetime.fromisoformat(accepted)
        if instant.tzinfo is None:
            raise ValueError()
        return utc(instant), str(UUID(message_id))
    except (ValueError, TypeError, binascii.Error, UnicodeError):
        raise DeliveryError('invalid_inbox_cursor') from None
