"""Native-domain behavioral fixtures: authenticated inputs, never relay trust."""

import json
from pathlib import Path

import pytest

from vipi.group_approval import (
    ApprovedRoster,
    ApprovalError,
    apply,
    may_receive,
    may_send,
)

FIXTURE = (
    Path(__file__).resolve().parents[2] / "docs" / "groups-approval-v1-fixtures.json"
)
CASES = json.loads(FIXTURE.read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda x: x["name"])
def test_control_authorization(case):
    previous = ApprovedRoster(case["group_id"], case["revision"], case["previous"])
    args = {
        "control_id": case["control_id"],
        "authenticated_actor": case["authenticated_actor"],
        "identity_pinned": case["identity_pinned"],
    }
    if case.get("error"):
        with pytest.raises(ApprovalError, match=case["error"]):
            apply(previous, case["control"], **args)
    else:
        result = apply(previous, case["control"], **args)
        assert result.members == case["control"]["members"]
        assert apply(result, case["control"], **args) == result
        if case["control"]["action"] != "leave":
            assert (
                may_send(result, result.members, actor_id=case["authenticated_actor"])
                == result.revision
            )


def test_server_only_addition_cannot_authorize_recipient():
    case = CASES[0]
    previous = ApprovedRoster(case["group_id"], case["revision"], case["previous"])
    with pytest.raises(ApprovalError, match="roster_approval_required"):
        may_send(
            previous, case["control"]["members"], actor_id=case["authenticated_actor"]
        )
    with pytest.raises(ApprovalError, match="message_membership_unapproved"):
        may_receive(
            previous,
            sender_id=case["control"]["target_id"],
            recipient_id=case["authenticated_actor"],
            revision=1,
        )


def test_explicit_invitee_anchor_uses_pinned_admin_and_exact_decrypted_roster():
    from vipi.group_approval import bootstrap

    case = CASES[0]
    args = dict(
        group_id=case["group_id"],
        control_id=case["control_id"],
        self_id=case["control"]["target_id"],
        authenticated_actor=case["authenticated_actor"],
        pinned_inviter=case["authenticated_actor"],
        identity_pinned=True,
        confirmed_members=case["control"]["members"],
    )
    assert bootstrap(case["control"], **args).revision == 2
    with pytest.raises(ApprovalError, match="explicit_roster_consent_required"):
        bootstrap(case["control"], **(args | {"confirmed_members": None}))
    with pytest.raises(ApprovalError, match="identity_confirmation_required"):
        bootstrap(case["control"], **(args | {"identity_pinned": False}))
    with pytest.raises(ApprovalError, match="identity_confirmation_required"):
        bootstrap(
            case["control"], **(args | {"pinned_inviter": case["control"]["target_id"]})
        )


def test_removed_member_cannot_send_with_historical_revision():
    case = next(c for c in CASES if c["name"] == "valid remove")
    approved = apply(
        ApprovedRoster(case["group_id"], case["revision"], case["previous"]),
        case["control"],
        control_id=case["control_id"],
        authenticated_actor=case["authenticated_actor"],
        identity_pinned=True,
    )
    with pytest.raises(ApprovalError, match="message_membership_unapproved"):
        may_receive(
            approved,
            sender_id=case["control"]["target_id"],
            recipient_id=case["authenticated_actor"],
            revision=1,
        )
    with pytest.raises(ApprovalError, match="message_membership_unapproved"):
        may_receive(
            approved,
            sender_id=case["control"]["target_id"],
            recipient_id=case["authenticated_actor"],
            revision=2,
        )
