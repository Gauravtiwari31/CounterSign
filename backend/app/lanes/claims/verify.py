"""Step 4 - Verify (code), non-negotiable. Citation validity is 100% by construction."""
from dataclasses import dataclass

from app.lanes.text import normalise
from app.lanes.types import Claim, FactRow
from app.schemas.llm import Verdict

MIN_QUOTE_CHARS = 6


@dataclass
class Checked:
    verdict: str  # supports | contradicts | insufficient
    fact: FactRow | None
    quote: str | None
    verified: bool
    downgraded: bool
    note: str | None
    difference: str | None
    explanation: str


def verify(claim: Claim, v: Verdict | None) -> Checked:
    if v is None:
        return Checked("insufficient", None, None, False, False, "The model returned no verdict for this claim", None, "")
    if v.verdict == "insufficient":
        return Checked("insufficient", None, None, False, False, None, v.difference, v.explanation)
    fact = next((f for f in claim.candidates if f.code == v.fact_code), None)
    quote = (v.evidence_quote or "").strip()
    nq = normalise(quote)
    ok = fact is not None and len(nq) >= MIN_QUOTE_CHARS and nq in normalise(fact.statement)
    if not ok:
        return Checked("insufficient", None, None, False, True,
                       "Model cited evidence that could not be verified", v.difference, v.explanation)
    return Checked(v.verdict, fact, quote, True, False, None, v.difference, v.explanation)
