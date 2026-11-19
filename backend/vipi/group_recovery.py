"""Executable native recovery-policy reference, not a relay or crypto routine.

Inputs follow successful envelope/context validation. `decrypted` means the
existing libsignal identity/session validation succeeded; callers must commit
Signal state, fingerprint, body or encrypted transport hold, and receipt in one
native vault transaction. This module makes no persistence/authentication claim.
"""
from enum import StrEnum

from .group_approval import ApprovalError, roster


class IncomingDisposition(StrEnum):
    DISPLAY = "display"
    WAIT_IDENTITY = "wait_identity"
    WAIT_BOOTSTRAP = "wait_bootstrap"
    WAIT_REVISION = "wait_revision"
    WITHHELD_OLD_REVISION = "withheld_old_revision"
    WITHHELD_MEMBERSHIP = "withheld_membership"
    ALREADY_COMMITTED = "already_committed"


def disposition(approved, *, revision, sender_id, recipient_id, identity_continuity,
                recorded_fingerprint=None, incoming_fingerprint=None):
    # A previously durable exact replay is history, even if the peer departed or
    # changed devices. It does not create another message/unread event/decrypt.
    if recorded_fingerprint is not None:
        if incoming_fingerprint is None or recorded_fingerprint != incoming_fingerprint:
            raise ApprovalError("envelope_context_changed")
        return IncomingDisposition.ALREADY_COMMITTED
    # No TOFU decrypt/display on a new or changed group sender identity.
    if not identity_continuity:
        return IncomingDisposition.WAIT_IDENTITY
    if type(revision) is not int or revision < 1:
        raise ApprovalError("invalid_group_revision")
    if approved is None:
        return IncomingDisposition.WAIT_BOOTSTRAP
    if revision > approved.revision:
        return IncomingDisposition.WAIT_REVISION
    if revision < approved.revision:
        return IncomingDisposition.WITHHELD_OLD_REVISION
    current = roster(approved.members, empty=True)
    if sender_id not in current or recipient_id not in current:
        return IncomingDisposition.WITHHELD_MEMBERSHIP
    return IncomingDisposition.DISPLAY
