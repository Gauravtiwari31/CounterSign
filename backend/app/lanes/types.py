import uuid
from dataclasses import dataclass, field
from datetime import date


@dataclass
class NewFinding:
    lane: str
    severity: str
    source: str
    start: int
    end: int
    span_text: str
    message: str
    explanation: str = ""
    rule_id: uuid.UUID | None = None
    rule_code: str | None = None
    criterion_code: str | None = None
    fact_ids: list[uuid.UUID] | None = None
    claim_type: str | None = None
    claim_text: str | None = None
    claim_label: str | None = None
    evidence: list[dict] = field(default_factory=list)
    regulatory_prompt: str | None = None
    suggestion: dict | None = None
    model: str | None = None
    prompt_version: str | None = None
    ai_fixable: bool = False


@dataclass
class FactRow:
    id: uuid.UUID
    code: str
    statement: str
    source_document: str
    source_locator: str
    owner: str
    valid_from: date | None
    valid_to: date | None
    superseded_by: uuid.UUID | None
    scope_products: list[str]
    scope_channels: list[str]
    scope_regions: list[str]
    superseded_by_code: str | None = None

    def status(self, today: date) -> str:
        if self.superseded_by:
            return "superseded"
        if self.valid_to and self.valid_to < today:
            return "expired"
        if self.valid_from and self.valid_from > today:
            return "not_yet_valid"
        return "valid"


@dataclass
class Claim:
    sentence_id: int
    start: int
    end: int
    quote: str
    claim_type: str
    atomic: str  # masked text, safe to send to the LLM
    product: str | None = None
    candidates: list[FactRow] = field(default_factory=list)
