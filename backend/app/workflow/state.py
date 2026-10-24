"""Draft state machine and guards. Pure functions so every transition x role is unit-testable.

DRAFT --submit version--> CHECKING --job done--> CHECKED
CHECKED --creator: send for countersign--> IN_REVIEW
IN_REVIEW --reviewer: request changes--> CHANGES_REQUESTED --new version--> CHECKING
IN_REVIEW --reviewer: approve--> APPROVED (terminal)
IN_REVIEW --reviewer: reject--> REJECTED (terminal)
"""
from dataclasses import dataclass

TERMINAL = {"approved", "rejected"}
EDITABLE = {"draft", "checking", "checked", "changes_requested"}

# status a draft must be in -> roles allowed, per action
TRANSITIONS = {
    "new_version": ({"draft", "checking", "checked", "changes_requested"}, {"creator", "admin"}),
    "send_for_review": ({"checked"}, {"creator", "admin"}),
    "approve": ({"in_review"}, {"reviewer", "admin"}),
    "reject": ({"in_review"}, {"reviewer", "admin"}),
    "request_changes": ({"in_review"}, {"reviewer", "admin"}),
}
TARGET = {"send_for_review": "in_review", "approve": "approved", "reject": "rejected",
          "request_changes": "changes_requested", "new_version": "checking"}


class TransitionError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class FindingView:
    lane: str
    severity: str
    status: str
    claim_label: str | None
    reviewer_overridden: bool = False


def check_transition(action: str, status: str, role: str, is_author: bool) -> str:
    allowed_from, roles = TRANSITIONS[action]
    if role not in roles:
        raise TransitionError(f"A {role} cannot {action.replace('_', ' ')}", 403)
    if role == "creator" and not is_author:
        raise TransitionError("Creators can only act on their own drafts", 403)
    if action == "approve" and is_author:
        # a countersign is a second person's signature
        raise TransitionError("You wrote this draft, so someone else must countersign it", 403)
    if status not in allowed_from:
        raise TransitionError(f"Cannot {action.replace('_', ' ')} while the draft is {status.replace('_', ' ')}")
    return TARGET[action]


def send_for_review_guard(findings: list[FindingView]) -> None:
    blocking = [f for f in findings if f.severity == "blocking"]
    unresolved = [f for f in blocking if f.status not in ("dismissed", "overridden", "resolved")]
    if unresolved:
        raise TransitionError(
            f"{len(unresolved)} blocking finding(s) still open. Fix and re-check, or dismiss with a reason.")


def approve_guard(findings: list[FindingView], claims_reviewed: bool) -> None:
    blocking = [f for f in findings if f.severity == "blocking"]
    open_ = [f for f in blocking if f.status in ("open", "accepted", "edited")]
    if open_:
        raise TransitionError(f"{len(open_)} blocking finding(s) are still open.")
    dismissed = [f for f in blocking if f.status == "dismissed" and not f.reviewer_overridden]
    if dismissed:
        raise TransitionError(
            f"{len(dismissed)} blocking finding(s) were dismissed by the creator. Override each with a reason first.")
    claims = [f for f in findings if f.lane == "claims"]
    if claims and not claims_reviewed:
        raise TransitionError(f'Tick "I have reviewed all {len(claims)} claims" before approving.')


FINDING_ACTIONS = {
    "accept": {"creator", "admin"},
    "edit": {"creator", "admin"},
    "dismiss": {"creator", "admin"},
    "override": {"reviewer", "admin"},
    "reopen": {"creator", "reviewer", "admin"},
}
FINDING_STATUS_AFTER = {"accept": "accepted", "edit": "edited", "dismiss": "dismissed", "override": "overridden",
                        "reopen": "open"}


def check_finding_action(action: str, role: str, is_author: bool, draft_status: str, severity: str,
                         reason: str | None) -> str:
    if action not in FINDING_ACTIONS:
        raise TransitionError(f"Unknown action {action}", 422)
    if role not in FINDING_ACTIONS[action]:
        raise TransitionError(f"A {role} cannot {action} findings", 403)
    if role == "creator" and not is_author:
        raise TransitionError("Creators can only act on their own drafts", 403)
    if draft_status in TERMINAL:
        raise TransitionError("This draft is closed")
    if action in ("accept", "edit", "dismiss") and role == "creator" and draft_status not in EDITABLE:
        raise TransitionError("The draft is with a reviewer; wait for a decision")
    if action in ("dismiss", "override") and severity == "blocking" and not (reason and reason.strip()):
        raise TransitionError("A reason is required to dismiss or override a blocking finding", 422)
    return FINDING_STATUS_AFTER[action]
