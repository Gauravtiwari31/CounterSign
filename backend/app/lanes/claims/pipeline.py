"""Claims lane: extract -> retrieve -> judge -> verify -> label, with a deterministic fallback."""
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.lanes.claims import heuristics
from app.lanes.claims.extract import extract_claims
from app.lanes.claims.judge import judge_claims
from app.lanes.claims.label import evidence_entry, label, regulatory_prompt
from app.lanes.claims.retrieve import retrieve
from app.lanes.claims.verify import verify
from app.lanes.context import ReviewContext
from app.lanes.text import Sentence
from app.lanes.types import Claim, NewFinding
from app.llm.adapter import LLMUnavailable
from app.pii import Masker


@dataclass
class ClaimsResult:
    findings: list[NewFinding]
    degraded: bool = False
    stats: dict = field(default_factory=dict)


def _guess_product(claim: Claim, sentence_text: str, products: list[str]) -> None:
    if claim.product:
        return
    low = sentence_text.lower()
    claim.product = next((p for p in products if p.lower() in low), None)


async def judge_and_label(session: AsyncSession, ctx: ReviewContext, claims: list[Claim],
                          sentences: list[Sentence]) -> tuple[list[NewFinding], dict]:
    by_id = {s.id: s for s in sentences}
    for c in claims:
        _guess_product(c, by_id[c.sentence_id].text if c.sentence_id in by_id else c.quote, ctx.product_names())
    await retrieve(session, ctx.org_id, ctx.facts_version, claims, ctx.channel, ctx.region, ctx.facts)
    verdicts, meta = await judge_claims(claims, ctx.cache_extra)
    findings, downgrades = [], 0
    for i, claim in enumerate(claims):
        checked = verify(claim, verdicts.get(i))
        downgrades += checked.downgraded
        findings.append(label(claim, checked, ctx.today, meta.model if meta else None,
                              meta.prompt_version if meta else None))
    return findings, {"verify_downgrades": downgrades, "judge_cached": bool(meta and meta.cached)}


async def run_claims(session: AsyncSession, ctx: ReviewContext, text: str, sentences: list[Sentence],
                     masker: Masker) -> ClaimsResult:
    try:
        claims, meta, dropped = await extract_claims(text, sentences, masker, ctx.cache_extra)
        findings, stats = await judge_and_label(session, ctx, claims, sentences)
        stats.update({"claims": len(claims), "unlocated_quotes_dropped": dropped, "model": meta.model if meta else None})
        return ClaimsResult(findings, False, stats)
    except LLMUnavailable as e:
        return await fallback(session, ctx, sentences, str(e))


async def fallback(session: AsyncSession, ctx: ReviewContext, sentences: list[Sentence], error: str) -> ClaimsResult:
    claims = heuristics.detect(sentences)
    for c in claims:
        _guess_product(c, c.quote, ctx.product_names())
    await retrieve(session, ctx.org_id, ctx.facts_version, claims, ctx.channel, ctx.region, ctx.facts)
    findings = []
    for c in claims:
        closest = [evidence_entry(f, None, False, ctx.today, role="candidate") for f in c.candidates[:3]]
        hint = f" Closest facts to check: {', '.join(f.code for f in c.candidates[:3])}." if c.candidates else ""
        findings.append(NewFinding(
            lane="claims", severity="blocking", source="pattern", start=c.start, end=c.end, span_text=c.quote,
            claim_type=c.claim_type, claim_text=c.quote, claim_label="UNSUPPORTED", evidence=closest,
            message="AI check unavailable: flagged by pattern, needs human review",
            explanation=heuristics.FALLBACK_NOTE + hint, regulatory_prompt=regulatory_prompt(c),
        ))
    return ClaimsResult(findings, True, {"claims": len(claims), "fallback_reason": error[:200]})
