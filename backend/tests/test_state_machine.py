"""Every transition x role, plus the guards."""
import itertools

import pytest

from app.workflow.state import (
    TRANSITIONS,
    FindingView,
    TransitionError,
    approve_guard,
    check_finding_action,
    check_transition,
    send_for_review_guard,
)

STATUSES = ["draft", "checking", "checked", "in_review", "changes_requested", "approved", "rejected"]
ROLES = ["creator", "reviewer", "admin"]

EXPECTED_OK = {
    ("new_version", s, r) for s in ("draft", "checking", "checked", "changes_requested") for r in ("creator", "admin")
} | {("send_for_review", "checked", r) for r in ("creator", "admin")} | {
    (a, "in_review", r) for a in ("approve", "reject", "request_changes") for r in ("reviewer", "admin")
}


@pytest.mark.parametrize("action,status,role", list(itertools.product(TRANSITIONS, STATUSES, ROLES)))
def test_transition_matrix(action, status, role):
    is_author = action != "approve"  # authorship rules have their own tests below
    if (action, status, role) in EXPECTED_OK:
        check_transition(action, status, role, is_author=is_author)
    else:
        with pytest.raises(TransitionError):
            check_transition(action, status, role, is_author=is_author)


@pytest.mark.parametrize("role", ["reviewer", "admin"])
def test_author_cannot_approve_own_draft(role):
    with pytest.raises(TransitionError) as e:
        check_transition("approve", "in_review", role, is_author=True)
    assert e.value.status_code == 403 and "someone else" in str(e.value)
    check_transition("reject", "in_review", role, is_author=True)  # sending back your own draft is fine


def test_creator_cannot_act_on_others_draft():
    with pytest.raises(TransitionError) as e:
        check_transition("send_for_review", "checked", "creator", is_author=False)
    assert e.value.status_code == 403


def F(severity="blocking", status="open", lane="rules", label=None):
    return FindingView(lane, severity, status, label, status == "overridden")


def test_send_guard():
    send_for_review_guard([F(status="resolved"), F(status="dismissed"), F("warning")])
    with pytest.raises(TransitionError):
        send_for_review_guard([F()])
    with pytest.raises(TransitionError):
        send_for_review_guard([F(status="accepted")])  # accepted but not re-checked


def test_approve_guard():
    approve_guard([F(status="overridden"), F("info", lane="claims")], claims_reviewed=True)
    with pytest.raises(TransitionError, match="dismissed by the creator"):
        approve_guard([F(status="dismissed")], claims_reviewed=True)
    with pytest.raises(TransitionError, match="reviewed all 1 claims"):
        approve_guard([F("info", lane="claims", status="open")], claims_reviewed=False)
    with pytest.raises(TransitionError, match="still open"):
        approve_guard([F()], claims_reviewed=True)


def test_finding_actions():
    assert check_finding_action("dismiss", "creator", True, "checked", "blocking", "Approved by legal") == "dismissed"
    assert check_finding_action("override", "reviewer", False, "in_review", "blocking", "OK per F-12") == "overridden"
    with pytest.raises(TransitionError):
        check_finding_action("dismiss", "creator", True, "checked", "blocking", "  ")
    with pytest.raises(TransitionError):
        check_finding_action("override", "creator", True, "checked", "blocking", "x")
    with pytest.raises(TransitionError):
        check_finding_action("accept", "creator", True, "approved", "warning", None)
    with pytest.raises(TransitionError):
        check_finding_action("dismiss", "creator", True, "in_review", "warning", None)
    assert check_finding_action("dismiss", "creator", True, "checked", "advisory", None) == "dismissed"
