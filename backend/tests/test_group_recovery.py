"""Policy ordering cases, not libsignal/vault or native execution tests."""
from dataclasses import replace

import pytest

from vipi.group_approval import ApprovedRoster, ApprovalError
from vipi.group_recovery import IncomingDisposition as D, disposition

OLD = ApprovedRoster("g",1,[{"user_id":"alice","role":"owner"},{"user_id":"bob","role":"member"},{"user_id":"eve","role":"member"}])
NEW = ApprovedRoster("g",2,[{"user_id":"alice","role":"owner"},{"user_id":"bob","role":"member"}])


def decide(approved=OLD,**fields):
    return disposition(approved,**(dict(revision=1,sender_id="eve",recipient_id="bob",identity_continuity=True)|fields))


def test_data_before_removal_stays_local_history_after_removal():
    assert decide() == D.DISPLAY
    assert decide(NEW,recorded_fingerprint="exact ciphertext/context",incoming_fingerprint="exact ciphertext/context") == D.ALREADY_COMMITTED
    with pytest.raises(ApprovalError,match="envelope_context_changed"):
        decide(NEW,recorded_fingerprint="original",incoming_fingerprint="replacement ciphertext under old ID")


def test_removal_before_late_data_does_not_automatically_authorize_old_chat():
    assert decide(NEW) == D.WITHHELD_OLD_REVISION
    # Same old membership/ID/time claims cannot revive it; advancing to current
    # revision cannot make a removed sender a member either.
    assert decide(NEW,revision=2) == D.WITHHELD_MEMBERSHIP


def test_late_legitimate_current_member_is_visible_withheld_then_new_id_resend():
    assert decide(NEW,sender_id="alice") == D.WITHHELD_OLD_REVISION
    # Resending is a fresh explicitly authorized message in latest revision,
    # never silently rewriting the old envelope's revision or fingerprint.
    assert decide(NEW,sender_id="alice",revision=2) == D.DISPLAY


def test_future_message_waits_for_control_and_can_recover_without_redecrypt():
    assert decide(OLD,sender_id="alice",revision=2) == D.WAIT_REVISION
    assert decide(NEW,sender_id="alice",revision=2) == D.DISPLAY


def test_bootstrap_arrival_order_requires_explicit_approved_state():
    assert decide(None,sender_id="alice",revision=2) == D.WAIT_BOOTSTRAP
    # A server roster/invitation/acceptance alone never supplies ApprovedRoster.
    assert decide(None,sender_id="alice",revision=2) == D.WAIT_BOOTSTRAP
    assert decide(NEW,sender_id="alice",revision=2) == D.DISPLAY


def test_control_chain_leaping_past_a_held_message_makes_it_visibly_withheld():
    assert decide(OLD,sender_id="alice",revision=2) == D.WAIT_REVISION
    assert decide(replace(NEW,revision=3),sender_id="alice",revision=2) == D.WITHHELD_OLD_REVISION


def test_device_identity_change_does_not_reclassify_already_delivered_history():
    assert decide(identity_continuity=False) == D.WAIT_IDENTITY
    assert decide(NEW,identity_continuity=False,recorded_fingerprint="same",incoming_fingerprint="same") == D.ALREADY_COMMITTED
    assert decide(NEW,sender_id="alice",revision=2,identity_continuity=False) == D.WAIT_IDENTITY


def test_invalid_revision_cannot_hide_as_future_pending_state():
    for revision in (True,0,-1,"2"):
        with pytest.raises(ApprovalError,match="invalid_group_revision"):
            decide(revision=revision)
