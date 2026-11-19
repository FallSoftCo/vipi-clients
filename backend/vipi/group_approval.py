"""Executable client-domain reference for Signal-authenticated roster controls.

NOT a server authentication routine. Its `authenticated_actor` and
`identity_pinned` inputs must come from successful existing libsignal decrypt
and a previously accepted identity pin, never HTTP metadata or server JSON.
Native implementations consume the same behavioral fixtures.
"""
from dataclasses import dataclass


class ApprovalError(ValueError):
    pass


def roster(value, *, empty=False):
    result = {}
    if not isinstance(value, list) or len(value) > 16:
        raise ApprovalError("invalid_roster")
    for member in value:
        if not isinstance(member, dict) or set(member) != {"user_id", "role"} or not isinstance(member["user_id"], str) or not member["user_id"]:
            raise ApprovalError("invalid_roster")
        user, role = member["user_id"], member["role"]
        if user in result or role not in ("owner", "admin", "member"):
            raise ApprovalError("invalid_roster")
        result[user] = role
    if (not result and not empty) or (result and list(result.values()).count("owner") != 1):
        raise ApprovalError("invalid_roster")
    return result


@dataclass(frozen=True)
class ApprovedRoster:
    group_id: str
    revision: int
    members: list[dict]
    control_id: str | None = None
    control: dict | None = None


def apply(previous, control, *, control_id, authenticated_actor, identity_pinned):
    """Only an already authenticated Signal message may reach this validator."""
    if not identity_pinned:
        raise ApprovalError("identity_confirmation_required")
    if not isinstance(control, dict):
        raise ApprovalError("invalid_control")
    if control.get("actor_id") != authenticated_actor:
        raise ApprovalError("actor_context_mismatch")
    required = {"actor_id", "action", "target_id", "from_revision", "to_revision", "server_epoch", "previous_members", "members"}
    allowed = required | ({"role"} if control.get("action") == "role" else set())
    if (set(control) != allowed or not isinstance(control_id, str) or not control_id or
            type(control.get("server_epoch")) is not int or control["server_epoch"] < 1):
        raise ApprovalError("invalid_control")
    if control.get("to_revision") == previous.revision:
        if previous.control_id == control_id and previous.control == control:
            return previous
        raise ApprovalError("conflicting_revision")
    if (type(control.get("from_revision")) is not int or type(control.get("to_revision")) is not int or
            control["from_revision"] != previous.revision or control["to_revision"] != previous.revision + 1):
        raise ApprovalError("missing_control_chain")
    old, supplied = roster(previous.members), roster(control.get("previous_members"))
    if old != supplied:
        raise ApprovalError("previous_roster_mismatch")
    new = roster(control.get("members"), empty=True)
    actor, target, action = authenticated_actor, control.get("target_id"), control.get("action")
    if actor not in old or not isinstance(target,str):
        raise ApprovalError("unauthorized_control")
    expected = dict(old)
    if action == "add":
        if old[actor] not in ("owner","admin") or target in old:
            raise ApprovalError("unauthorized_control")
        expected[target] = "member"
    elif action == "remove":
        if (old[actor] not in ("owner","admin") or target not in old or target == actor or
                old[target] == "owner" or (old[actor] == "admin" and old[target] != "member")):
            raise ApprovalError("unauthorized_control")
        del expected[target]
    elif action == "role":
        role = control.get("role")
        if old[actor] != "owner" or target not in old or target == actor or old[target] == "owner" or role not in ("admin","member"):
            raise ApprovalError("unauthorized_control")
        expected[target] = role
    elif action == "transfer":
        if old[actor] != "owner" or target not in old or target == actor:
            raise ApprovalError("unauthorized_control")
        expected[actor], expected[target] = "admin", "owner"
    elif action == "leave":
        if target != actor or (old[actor] == "owner" and len(old) > 1):
            raise ApprovalError("explicit_owner_transfer_required")
        del expected[actor]
    else:
        raise ApprovalError("invalid_control_action")
    if expected != new:
        raise ApprovalError("unexpected_roster_delta")
    return ApprovedRoster(previous.group_id,control["to_revision"],control["members"],control_id,control)


def may_send(approved, relay_members, *, actor_id):
    expected, actual = roster(approved.members), roster(relay_members)
    if expected != actual or actor_id not in expected:
        raise ApprovalError("roster_approval_required")
    return approved.revision


def may_receive(approved, *, sender_id, recipient_id, revision):
    current = roster(approved.members)
    if type(revision) is not int or revision != approved.revision or sender_id not in current or recipient_id not in current:
        raise ApprovalError("message_membership_unapproved")
    return True


def bootstrap(control, *, group_id, control_id, self_id, authenticated_actor,
              pinned_inviter, identity_pinned, confirmed_members):
    """Explicit new-member trust anchor, never automatic relay reconstruction.

    `confirmed_members` is the exact decrypted roster accepted in native review,
    not a server-supplied list passed through without user action.
    """
    if not identity_pinned or not pinned_inviter or authenticated_actor != pinned_inviter:
        raise ApprovalError("identity_confirmation_required")
    if control.get("action") != "add" or control.get("target_id") != self_id:
        raise ApprovalError("invalid_join_anchor")
    if confirmed_members is None or roster(confirmed_members) != roster(control.get("members")):
        raise ApprovalError("explicit_roster_consent_required")
    old = roster(control.get("previous_members"))
    if old.get(authenticated_actor) not in ("owner", "admin") or self_id in old:
        raise ApprovalError("invalid_join_anchor")
    revision = control.get("from_revision")
    if type(revision) is not int or revision < 1:
        raise ApprovalError("invalid_join_anchor")
    previous = ApprovedRoster(group_id,revision,control["previous_members"])
    return apply(previous,control,control_id=control_id,authenticated_actor=authenticated_actor,identity_pinned=True)
