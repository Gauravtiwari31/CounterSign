"""Review orchestration: rules inline on submit, AI lanes in the worker, findings persisted per version."""
import asyncio
import hashlib
import time
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_event
from app.lanes.claims.pipeline import run_claims
from app.lanes.context import ReviewContext, build_context
from app.lanes.fixes.generate import ai_fixes, deterministic_suggestion, guard_voice_suggestions
from app.lanes.rules.engine import run_rules
from app.lanes.text import canonical, normalise, split_sentences
from app.lanes.types import NewFinding
from app.lanes.voice.review import run_voice
from app.llm.adapter import LLMUnavailable
from app.models import Draft, DraftVersion, Finding, Organization, ReviewJob, User, utcnow
from app.pii import Masker

AI_FIXABLE_RULE_TYPES = {"banned_phrase", "readability", "regex"}

def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def rules_lane(text: str, ctx: ReviewContext) -> list[NewFinding]:
    findings = []
    for h in run_rules(text, ctx.channel, ctx.rules):
        f = NewFinding(
            lane="rules", severity=h.severity, source="rule", start=h.start, end=h.end, span_text=h.span_text,
            message=h.message, explanation=h.explanation, rule_id=uuid.UUID(h.rule_id) if h.rule_id else None,
            rule_code=h.code, ai_fixable=h.ai_fixable,
        )
        if h.replacement is not None:
            f.suggestion = deterministic_suggestion(f, h.replacement, text, ctx)
        findings.append(f)
    return findings


def to_row(version_id: uuid.UUID, f: NewFinding) -> Finding:
    return Finding(
        draft_version_id=version_id, lane=f.lane, severity=f.severity, source=f.source, start=f.start, end=f.end,
        span_text=f.span_text, rule_id=f.rule_id, rule_code=f.rule_code, criterion_code=f.criterion_code,
        fact_ids=f.fact_ids, claim_type=f.claim_type, claim_text=f.claim_text, claim_label=f.claim_label,
        evidence=f.evidence, message=f.message, explanation=f.explanation, regulatory_prompt=f.regulatory_prompt,
        suggestion=f.suggestion, model=f.model, prompt_version=f.prompt_version,
    )


def _match_key(f: Finding) -> tuple:
    return (f.lane, f.rule_code, f.criterion_code, f.claim_label, normalise(f.span_text))


async def carry_over_decisions(session: AsyncSession, draft_id: uuid.UUID, version_no: int, rows: list[Finding]) -> None:
    """Dismissals/overrides on the previous version stick to the same finding on the new version."""
    if version_no <= 1:
        return
    prev = await session.scalar(select(DraftVersion).where(DraftVersion.draft_id == draft_id,
                                                           DraftVersion.version_no == version_no - 1))
    if prev is None:
        return
    decided = (await session.scalars(select(Finding).where(
        Finding.draft_version_id == prev.id, Finding.status.in_(("dismissed", "overridden"))))).all()
    by_key = {_match_key(f): f for f in decided}
    for row in rows:
        old = by_key.get(_match_key(row))
        if old is not None:
            row.status = old.status
            row.carried_from = old.id


async def create_version(session: AsyncSession, org: Organization, draft: Draft, user: User, text: str,
                         source_type: str = "paste", file_id: uuid.UUID | None = None,
                         inline: bool = False) -> DraftVersion:
    """Store a version, run the rules lane inline, queue the AI lanes (or mark them running for an inline caller)."""
    text = canonical(text)
    draft.current_version_no += 1
    version = DraftVersion(
        draft_id=draft.id, version_no=draft.current_version_no, text=text, source_type=source_type, file_id=file_id,
        text_hash=text_hash(text), rulebook_version=org.rulebook_version, facts_version=org.facts_version,
        created_by=user.id,
    )
    session.add(version)
    await session.flush()

    t0 = time.perf_counter()
    ctx = await build_context(session, org, draft.channel, draft.purpose, version.rulebook_version, version.facts_version)
    rows = [to_row(version.id, f) for f in rules_lane(text, ctx)]
    rules_ms = round((time.perf_counter() - t0) * 1000, 1)
    await carry_over_decisions(session, draft.id, version.version_no, rows)
    session.add_all(rows)
    now = utcnow()
    session.add(ReviewJob(
        draft_version_id=version.id, status="running" if inline else "queued",
        locked_at=now if inline else None, started_at=now if inline else None, attempts=1 if inline else 0,
        lane_status={"rules": "done", "claims": "queued", "voice": "queued", "fixes": "queued"},
        timings={"rules_ms": rules_ms},
    ))
    draft.status = "checking"
    draft.updated_at = utcnow()
    await append_event(session, org.id, user.id, "draft", draft.id, "version.created",
                       {"version_no": version.version_no, "source_type": source_type, "text_hash": version.text_hash,
                        "rulebook_version": version.rulebook_version, "facts_version": version.facts_version,
                        "rule_findings": len(rows)})
    return version


async def _set_lanes(session: AsyncSession, job: ReviewJob, **lanes) -> None:
    job.lane_status = {**job.lane_status, **lanes}
    await session.commit()


async def run_ai_lanes(session: AsyncSession, job: ReviewJob) -> None:
    version = await session.get(DraftVersion, job.draft_version_id)
    draft = await session.get(Draft, version.draft_id)
    org = await session.get(Organization, draft.org_id)
    ctx = await build_context(session, org, draft.channel, draft.purpose, version.rulebook_version, version.facts_version)
    text = version.text
    sentences = split_sentences(text)
    masker = Masker(ctx.allow_terms())
    timings = dict(job.timings or {})

    await _set_lanes(session, job, claims="running", voice="running")
    t0 = time.perf_counter()

    async def _voice():
        try:
            return await run_voice(text, ctx.criteria, masker, ctx.cache_extra), "done"
        except LLMUnavailable:
            return [], "unavailable"

    claims_result, (voice_findings, voice_state) = await asyncio.gather(
        run_claims(session, ctx, text, sentences, masker), _voice()
    )
    timings["claims_voice_ms"] = round((time.perf_counter() - t0) * 1000)
    await _set_lanes(session, job, claims="degraded" if claims_result.degraded else "done", voice=voice_state,
                     fixes="running")

    # rule findings (already stored) that need an AI rewrite join the batched fix call
    stored_rules = (await session.scalars(select(Finding).where(
        Finding.draft_version_id == version.id, Finding.lane == "rules"))).all()
    ai_fixable_codes = {r.code for r in ctx.rules if r.type in AI_FIXABLE_RULE_TYPES}
    rule_views = []
    for r in stored_rules:
        nf = NewFinding(lane="rules", severity=r.severity, source="rule", start=r.start, end=r.end,
                        span_text=r.span_text, message=r.message, explanation=r.explanation, rule_code=r.rule_code,
                        suggestion=r.suggestion, ai_fixable=r.suggestion is None and r.rule_code in ai_fixable_codes)
        rule_views.append((r, nf))

    t1 = time.perf_counter()
    new_findings = claims_result.findings + voice_findings
    guard_voice_suggestions(voice_findings, text, ctx)
    fix_stats = await ai_fixes(session, ctx, text, [nf for _, nf in rule_views] + claims_result.findings, masker)
    timings["fixes_ms"] = round((time.perf_counter() - t1) * 1000)
    for row, nf in rule_views:
        if nf.suggestion is not row.suggestion:
            row.suggestion = nf.suggestion

    rows = [to_row(version.id, f) for f in new_findings]
    await carry_over_decisions(session, draft.id, version.version_no, rows)
    session.add_all(rows)
    job.status = "done"
    job.ai_degraded = claims_result.degraded or voice_state != "done"
    job.finished_at = utcnow()
    timings["total_ms"] = round((job.finished_at - job.started_at).total_seconds() * 1000) if job.started_at else None
    job.timings = {**timings, "claims": claims_result.stats, "fixes": fix_stats}
    job.lane_status = {**job.lane_status, "fixes": "done"}
    if draft.status == "checking" and draft.current_version_no == version.version_no:
        draft.status = "checked"
        draft.updated_at = utcnow()
    await append_event(session, org.id, None, "draft", draft.id, "review.completed",
                       {"version_no": version.version_no, "findings": len(rows) + len(stored_rules),
                        "ai_degraded": job.ai_degraded})
    await session.commit()


async def retry_ai(session: AsyncSession, version: DraftVersion) -> ReviewJob:
    """Drop AI-lane findings and re-queue (used by the 'Retry AI checks' banner)."""
    job = await session.scalar(select(ReviewJob).where(ReviewJob.draft_version_id == version.id))
    await session.execute(Finding.__table__.delete().where(
        Finding.draft_version_id == version.id, Finding.lane.in_(("claims", "voice"))))
    await session.execute(update(Finding).where(Finding.draft_version_id == version.id, Finding.lane == "rules",
                                                Finding.suggestion["kind"].astext == "ai").values(suggestion=None))
    job.status = "queued"
    job.attempts = 0
    job.error = None
    job.lane_status = {"rules": "done", "claims": "queued", "voice": "queued", "fixes": "queued"}
    draft = await session.get(Draft, version.draft_id)
    if draft.current_version_no == version.version_no and draft.status == "checked":
        draft.status = "checking"
    return job
