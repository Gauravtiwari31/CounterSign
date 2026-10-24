"""Compact AI review: one call extracts and judges claims, writes voice notes and proposes fixes.

Built for small request quotas. The model's output goes through the same code checks as the full pipeline:
quotes are located in the draft or dropped, evidence quotes are verified word for word against facts that
code retrieved for that sentence, expiry and severity are decided in code, and voice severity is fixed.
"""
import json
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.lanes.claims.label import label
from app.lanes.claims.pipeline import ClaimsResult, _guess_product, fallback
from app.lanes.claims.retrieve import in_scope, retrieve
from app.lanes.claims.verify import verify
from app.lanes.context import ReviewContext
from app.lanes.text import Sentence, locate
from app.lanes.types import Claim, FactRow, NewFinding
from app.lanes.voice.review import notes_to_findings
from app.llm import adapter
from app.llm.adapter import LLMUnavailable
from app.llm.prompts import REVIEW_COMPACT_SYSTEM, REVIEW_COMPACT_VERSION
from app.models import VoiceCriterion
from app.pii import Masker
from app.schemas.llm import CompactOut, Verdict

MAX_FACTS = 30
EXPIRED_APPROACH = ("the approved fact behind this claim is no longer current. Remove the claim, or ask the fact "
                    "owner for an updated fact and use its wording.")


@dataclass
class CompactResult:
    claims: ClaimsResult
    voice: list[NewFinding]
    voice_state: str
    # id(finding) -> (replacement, approach); None when the AI call failed
    proposals: dict[int, tuple[str | None, str | None]] | None = field(default_factory=dict)


async def sentence_facts(session: AsyncSession, ctx: ReviewContext, sentences: list[Sentence],
                         masker: Masker) -> tuple[dict[int, list[FactRow]], list[FactRow]]:
    """Candidate facts per sentence, chosen by code (not the model) so one prompt can carry them all.

    A small library is sent whole: sentence-level retrieval misses facts that a claim paraphrases, and every
    fact costs only a few tokens. Product scope is still applied per claim before verification.
    """
    scoped = [f for f in ctx.facts.values() if in_scope(f, None, ctx.channel, ctx.region)]
    if len(scoped) <= MAX_FACTS:
        scoped.sort(key=lambda f: f.code)
        return {s.id: scoped for s in sentences}, scoped
    probes = []
    for s in sentences:
        c = Claim(sentence_id=s.id, start=s.start, end=s.end, quote=s.text, claim_type="other", atomic=masker.mask(s.text))
        _guess_product(c, s.text, ctx.product_names())
        probes.append(c)
    await retrieve(session, ctx.org_id, ctx.facts_version, probes, ctx.channel, ctx.region, ctx.facts)
    per_sentence = {c.sentence_id: c.candidates for c in probes}
    union: dict = {}
    for c in probes:
        for f in c.candidates:
            union.setdefault(f.id, f)
    return per_sentence, list(union.values())[:MAX_FACTS]


def _fact_entry(f: FactRow) -> dict:
    # no validity status: shown an expired fact, models call a matching claim "contradicted"; expiry is code's job
    return {"fact_code": f.code, "statement": f.statement}


def build_user_prompt(ctx: ReviewContext, sentences: list[Sentence], per_sentence: dict[int, list[FactRow]],
                      facts: list[FactRow], criteria: list[VoiceCriterion], rule_targets: list[NewFinding],
                      masker: Masker) -> str:
    numbered = "\n".join(f"[{s.id}] {masker.mask(s.text)}" for s in sentences)
    every = len(facts)
    per = {s.id: "all" if len(per_sentence.get(s.id, [])) == every else [f.code for f in per_sentence.get(s.id, [])]
           for s in sentences}
    parts = [
        f"Purpose line: {ctx.purpose}",
        "Approved facts:\n" + json.dumps([_fact_entry(f) for f in facts], ensure_ascii=False),
        "Facts to judge each sentence against: " + json.dumps(per),
    ]
    if criteria:
        parts.append("Voice rubric:\n" + json.dumps(
            [{"code": c.code, "title": c.title, "description": c.description, "good": c.good_examples,
              "bad": c.bad_examples} for c in criteria], ensure_ascii=False))
    if rule_targets:
        parts.append("Rule findings to fix:\n" + json.dumps(
            [{"finding_index": i, "flagged_span": masker.mask(f.span_text), "problem": f.message}
             for i, f in enumerate(rule_targets)], ensure_ascii=False))
    parts.append(f"Numbered sentences of the draft:\n<draft>\n{numbered}\n</draft>")
    return "\n\n".join(parts)


async def run_compact(session: AsyncSession, ctx: ReviewContext, text: str, sentences: list[Sentence],
                      masker: Masker, rule_targets: list[NewFinding]) -> CompactResult:
    if not sentences:
        return CompactResult(ClaimsResult([]), [], "done")
    per_sentence, facts = await sentence_facts(session, ctx, sentences, masker)
    try:
        out, meta = await adapter.generate_json(
            system=REVIEW_COMPACT_SYSTEM,
            user=build_user_prompt(ctx, sentences, per_sentence, facts, ctx.criteria, rule_targets, masker),
            schema=CompactOut, prompt_version=REVIEW_COMPACT_VERSION, cache_extra=ctx.cache_extra,
        )
    except LLMUnavailable as e:
        return CompactResult(await fallback(session, ctx, sentences, str(e)), [], "unavailable", None)

    by_id = {s.id: s for s in sentences}
    findings, proposals = [], {}
    seen: set[tuple[int, int]] = set()
    dropped = downgrades = 0
    for c in out.claims:
        sent = by_id.get(c.sentence_id)
        span = locate(masker.unmask(c.quote), text, (sent.start, sent.end)) if sent else None
        if span is None:
            dropped += 1
            continue
        if span in seen:
            continue
        seen.add(span)
        claim = Claim(sentence_id=c.sentence_id, start=span[0], end=span[1], quote=text[span[0]:span[1]],
                      claim_type=c.claim_type, atomic=c.atomic_claim, product=masker.unmask(c.product))
        _guess_product(claim, sent.text, ctx.product_names())
        # the model may only cite facts code retrieved for this sentence and that fit the claim's product
        claim.candidates = [f for f in per_sentence.get(c.sentence_id, [])
                            if in_scope(f, claim.product, ctx.channel, ctx.region)]
        checked = verify(claim, Verdict(claim_index=0, verdict=c.verdict, fact_code=c.fact_code,
                                        evidence_quote=c.evidence_quote, difference=c.difference,
                                        explanation=c.explanation))
        downgrades += checked.downgraded
        finding = label(claim, checked, ctx.today, meta.model, meta.prompt_version)
        findings.append(finding)
        if finding.claim_label == "EXPIRED":
            proposals[id(finding)] = (None, EXPIRED_APPROACH)
        else:
            proposals[id(finding)] = (masker.unmask(c.replacement) if c.replacement else None, c.approach)
    for fx in out.rule_fixes:
        if 0 <= fx.finding_index < len(rule_targets):
            proposals[id(rule_targets[fx.finding_index])] = (
                masker.unmask(fx.replacement) if fx.replacement else None, fx.approach)

    voice = notes_to_findings(out.voice_notes, ctx.criteria, text, masker, meta)
    stats = {"claims": len(findings), "unlocated_quotes_dropped": dropped, "verify_downgrades": downgrades,
             "model": meta.model, "judge_cached": meta.cached, "mode": "compact", "facts_sent": len(facts)}
    return CompactResult(ClaimsResult(findings, False, stats), voice, "done", proposals)
