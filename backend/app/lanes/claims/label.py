"""Step 5 - Label (code) + deterministic regulatory review prompts."""
from datetime import date

from app.lanes.claims.verify import Checked
from app.lanes.types import Claim, FactRow, NewFinding

NOT_LEGAL_ADVICE = "Review prompt, not legal advice."
REGULATORY_PROMPTS = {
    "environmental": "Environmental claims must be specific and substantiated (CCPA Guidelines for Prevention and "
                     "Regulation of Greenwashing, 2024). " + NOT_LEGAL_ADVICE,
    "health_benefit": "Health and efficacy claims need substantiation (ASCI Code, Chapter I). " + NOT_LEGAL_ADVICE,
    "free_offer": "'Free' offers must state any conditions clearly (ASCI Code). " + NOT_LEGAL_ADVICE,
    "comparative": "Comparisons must be fair and substantiated (ASCI Code, Chapter IV). " + NOT_LEGAL_ADVICE,
    "price_offer": "Price and discount claims must be accurate and current (CCPA dark-patterns and misleading "
                   "ads guidelines). " + NOT_LEGAL_ADVICE,
    "certification_award": "Certifications and awards need a verifiable source. " + NOT_LEGAL_ADVICE,
}
CLINICAL_WORDS = ("clinically", "proven", "dermatologist", "tested")


def regulatory_prompt(claim: Claim) -> str | None:
    prompt = REGULATORY_PROMPTS.get(claim.claim_type)
    if prompt is None and any(w in claim.quote.lower() for w in CLINICAL_WORDS):
        prompt = REGULATORY_PROMPTS["health_benefit"]
    return prompt


def evidence_entry(fact: FactRow, quote: str | None, verified: bool, today: date, role: str = "cited") -> dict:
    return {
        "fact_id": str(fact.id), "fact_code": fact.code, "statement": fact.statement, "quote": quote,
        "verified": verified, "owner": fact.owner, "source_document": fact.source_document,
        "source_locator": fact.source_locator, "valid_to": fact.valid_to.isoformat() if fact.valid_to else None,
        "status": fact.status(today), "superseded_by": fact.superseded_by_code, "role": role,
    }


def label(claim: Claim, checked: Checked, today: date, model: str | None, prompt_version: str | None) -> NewFinding:
    base = dict(
        lane="claims", source="ai", start=claim.start, end=claim.end, span_text=claim.quote,
        claim_type=claim.claim_type, claim_text=claim.atomic, regulatory_prompt=regulatory_prompt(claim),
        model=model, prompt_version=prompt_version,
    )
    closest = ", ".join(f.code for f in claim.candidates[:3])
    fact = checked.fact
    if checked.verdict == "insufficient" or fact is None:
        why = checked.note or "No approved fact clearly backs this claim."
        if closest:
            why += f" Closest facts checked: {closest}."
        if checked.explanation and not checked.downgraded:
            why = checked.explanation + " " + why
        return NewFinding(severity="blocking", claim_label="UNSUPPORTED", message="No approved evidence supports this claim",
                          explanation=why.strip(), **base)

    ev = [evidence_entry(fact, checked.quote, True, today)]
    detail = checked.explanation or ""
    if checked.difference:
        detail = (detail + f" Difference: {checked.difference}.").strip()
    status = fact.status(today)
    if checked.verdict == "contradicts":
        return NewFinding(severity="blocking", claim_label="CONTRADICTED", fact_ids=[fact.id], evidence=ev,
                          message=f"Contradicted by approved fact {fact.code}", explanation=detail, **base)
    if status in ("expired", "superseded"):
        when = (f"expired on {fact.valid_to.isoformat()}" if status == "expired"
                else f"was superseded by {fact.superseded_by_code or 'a newer fact'}")
        return NewFinding(severity="blocking", claim_label="EXPIRED", fact_ids=[fact.id], evidence=ev,
                          message=f"Relies on {fact.code}, which {when}",
                          explanation=(detail + " The evidence is no longer current, so the claim cannot be used as written.").strip(),
                          **base)
    if status == "not_yet_valid":
        return NewFinding(severity="blocking", claim_label="UNSUPPORTED", fact_ids=[fact.id], evidence=ev,
                          message=f"{fact.code} is not valid until {fact.valid_from.isoformat()}",
                          explanation=detail, **base)
    return NewFinding(severity="info", claim_label="SUPPORTED", fact_ids=[fact.id], evidence=ev,
                      message=f"Supported by approved fact {fact.code}", explanation=detail, **base)
