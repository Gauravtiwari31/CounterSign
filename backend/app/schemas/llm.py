"""Pydantic schemas for every LLM response. Anything that does not validate is rejected."""
from typing import Literal

from pydantic import BaseModel, Field

ClaimType = Literal[
    "numeric", "comparative", "health_benefit", "environmental", "price_offer", "free_offer",
    "certification_award", "other",
]


class ExtractedClaim(BaseModel):
    sentence_id: int
    quote: str = Field(description="Exact words copied from the sentence")
    claim_type: ClaimType
    atomic_claim: str
    product: str | None = None


class ExtractOut(BaseModel):
    claims: list[ExtractedClaim] = Field(default_factory=list)


class Verdict(BaseModel):
    claim_index: int
    verdict: Literal["supports", "contradicts", "insufficient"]
    fact_code: str | None = None
    evidence_quote: str | None = None
    difference: str | None = None
    explanation: str = ""


class JudgeOut(BaseModel):
    verdicts: list[Verdict] = Field(default_factory=list)


class VoiceNote(BaseModel):
    criterion_code: str
    quote: str
    note: str
    suggestion: str | None = None


class VoiceOut(BaseModel):
    notes: list[VoiceNote] = Field(default_factory=list, max_length=5)


class FixOut(BaseModel):
    class Fix(BaseModel):
        finding_index: int
        replacement: str | None = None
        approach: str | None = Field(None, description="If no safe rewrite exists, how a human should fix it")

    fixes: list[Fix] = Field(default_factory=list)


class IntentOut(BaseModel):
    class Score(BaseModel):
        fix_index: int
        intent_score: int = Field(ge=1, le=5)

    scores: list[Score] = Field(default_factory=list)
