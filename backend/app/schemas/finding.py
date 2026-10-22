"""The Finding contract shared by backend, frontend and eval."""
import uuid
from typing import Literal

from pydantic import BaseModel

from app.models import Finding

Lane = Literal["rules", "claims", "voice"]
Severity = Literal["blocking", "warning", "advisory", "info"]
ClaimLabel = Literal["SUPPORTED", "UNSUPPORTED", "CONTRADICTED", "EXPIRED"]


class Span(BaseModel):
    start: int
    end: int
    text: str


class RuleRef(BaseModel):
    id: uuid.UUID | None
    code: str | None


class ClaimInfo(BaseModel):
    type: str | None
    text: str | None
    label: ClaimLabel | None


class Evidence(BaseModel):
    fact_id: str | None = None
    fact_code: str
    statement: str | None = None
    quote: str | None = None
    verified: bool
    owner: str | None = None
    source_document: str | None = None
    source_locator: str | None = None
    valid_to: str | None = None
    status: str
    superseded_by: str | None = None
    role: str = "cited"


class Recheck(BaseModel):
    rules_ok: bool | None = None
    claims_ok: bool | None = None
    intent_score: int | None = None


class Suggestion(BaseModel):
    replacement: str | None
    kind: Literal["deterministic", "ai"]
    approach: str | None = None
    recheck: Recheck | None = None


class FindingOut(BaseModel):
    id: uuid.UUID
    lane: Lane
    severity: Severity
    source: Literal["rule", "ai", "pattern"]
    span: Span
    rule: RuleRef | None
    criterion_code: str | None
    claim: ClaimInfo | None
    evidence: list[Evidence]
    message: str
    explanation: str
    regulatory_prompt: str | None
    suggestion: Suggestion | None
    status: str
    carried_over: bool
    model: str | None
    prompt_version: str | None

    @classmethod
    def from_row(cls, f: Finding) -> "FindingOut":
        return cls(
            id=f.id, lane=f.lane, severity=f.severity, source=f.source,
            span=Span(start=f.start, end=f.end, text=f.span_text),
            rule=RuleRef(id=f.rule_id, code=f.rule_code) if f.rule_code else None,
            criterion_code=f.criterion_code,
            claim=ClaimInfo(type=f.claim_type, text=f.claim_text, label=f.claim_label) if f.lane == "claims" else None,
            evidence=[Evidence(**e) for e in (f.evidence or [])],
            message=f.message, explanation=f.explanation or "", regulatory_prompt=f.regulatory_prompt,
            suggestion=Suggestion(**f.suggestion) if f.suggestion else None,
            status=f.status, carried_over=f.carried_from is not None, model=f.model, prompt_version=f.prompt_version,
        )


SEVERITY_ORDER = {"blocking": 0, "warning": 1, "advisory": 2, "info": 3}


def sort_key(f: Finding) -> tuple:
    return (SEVERITY_ORDER.get(f.severity, 9), f.start, f.lane)
