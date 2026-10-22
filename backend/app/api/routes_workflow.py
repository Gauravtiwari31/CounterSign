import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import current_version, draft_or_404, user_names
from app.audit import append_event, verify_chain
from app.db import get_session
from app.deps import Principal, current_principal
from app.models import AuditEvent, Comment, DraftVersion, Finding, FindingDecision, ReviewJob, WorkflowDecision
from app.workflow.state import FindingView, TransitionError, approve_guard, check_transition, send_for_review_guard

router = APIRouter(prefix="/api", tags=["workflow"])


async def _finding_views(session: AsyncSession, version_id: uuid.UUID) -> list[FindingView]:
    findings = (await session.scalars(select(Finding).where(Finding.draft_version_id == version_id))).all()
    return [FindingView(f.lane, f.severity, f.status, f.claim_label, f.status == "overridden") for f in findings]


@router.post("/drafts/{draft_id}/send-for-review")
async def send_for_review(draft_id: uuid.UUID, p: Principal = Depends(current_principal),
                          session: AsyncSession = Depends(get_session)):
    draft = await draft_or_404(session, p, draft_id, lock=True)
    try:
        target = check_transition("send_for_review", draft.status, p.role, draft.author_id == p.user.id)
        version = await current_version(session, draft)
        job = await session.scalar(select(ReviewJob).where(ReviewJob.draft_version_id == version.id))
        if job is None or job.status != "done":
            raise TransitionError("Checks are still running for this version")
        send_for_review_guard(await _finding_views(session, version.id))
    except TransitionError as e:
        raise HTTPException(e.status_code, str(e)) from e
    draft.status = target
    session.add(WorkflowDecision(draft_id=draft.id, version_no=draft.current_version_no, actor_id=p.user.id,
                                 decision="submitted"))
    await append_event(session, p.org_id, p.user.id, "draft", draft.id, "workflow.submitted",
                       {"version_no": draft.current_version_no})
    await session.commit()
    return {"status": draft.status}


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject", "request_changes"]
    reason: str | None = Field(None, max_length=2000)
    claims_reviewed: bool = False


DECISION_RECORD = {"approve": "approved", "reject": "rejected", "request_changes": "changes_requested"}


@router.post("/drafts/{draft_id}/decision")
async def decide(draft_id: uuid.UUID, body: DecisionIn, p: Principal = Depends(current_principal),
                 session: AsyncSession = Depends(get_session)):
    draft = await draft_or_404(session, p, draft_id, lock=True)
    try:
        target = check_transition(body.decision, draft.status, p.role, draft.author_id == p.user.id)
        if body.decision in ("reject", "request_changes") and not (body.reason and body.reason.strip()):
            raise TransitionError("A reason is required", 422)
        version = await current_version(session, draft)
        if body.decision == "approve":
            approve_guard(await _finding_views(session, version.id), body.claims_reviewed)
    except TransitionError as e:
        raise HTTPException(e.status_code, str(e)) from e
    draft.status = target
    record = DECISION_RECORD[body.decision]
    session.add(WorkflowDecision(draft_id=draft.id, version_no=draft.current_version_no, actor_id=p.user.id,
                                 decision=record, reason=body.reason, claims_reviewed=body.claims_reviewed))
    await append_event(session, p.org_id, p.user.id, "draft", draft.id, f"workflow.{record}",
                       {"version_no": draft.current_version_no, "reason": body.reason,
                        "claims_reviewed": body.claims_reviewed})
    await session.commit()
    return {"status": draft.status}


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    finding_id: uuid.UUID | None = None


@router.get("/drafts/{draft_id}/comments")
async def list_comments(draft_id: uuid.UUID, p: Principal = Depends(current_principal),
                        session: AsyncSession = Depends(get_session)):
    draft = await draft_or_404(session, p, draft_id)
    users = await user_names(session, p.org_id)
    comments = (await session.scalars(select(Comment).where(Comment.draft_id == draft.id)
                                      .order_by(Comment.created_at))).all()
    return [{"id": str(c.id), "version_no": c.version_no, "author": users.get(c.author_id), "body": c.body,
             "finding_id": str(c.finding_id) if c.finding_id else None, "created_at": c.created_at.isoformat()}
            for c in comments]


@router.post("/drafts/{draft_id}/comments", status_code=201)
async def add_comment(draft_id: uuid.UUID, body: CommentIn, p: Principal = Depends(current_principal),
                      session: AsyncSession = Depends(get_session)):
    draft = await draft_or_404(session, p, draft_id)
    if body.finding_id:
        owner = await session.scalar(select(DraftVersion.draft_id).join(Finding, Finding.draft_version_id == DraftVersion.id)
                                     .where(Finding.id == body.finding_id))
        if owner != draft.id:
            raise HTTPException(404, "Finding not found")
    c = Comment(draft_id=draft.id, version_no=draft.current_version_no, author_id=p.user.id, body=body.body.strip(),
                finding_id=body.finding_id)
    session.add(c)
    await session.flush()
    await append_event(session, p.org_id, p.user.id, "draft", draft.id, "comment.added",
                       {"comment_id": str(c.id), "version_no": c.version_no})
    await session.commit()
    return {"id": str(c.id)}


@router.get("/drafts/{draft_id}/history")
async def history(draft_id: uuid.UUID, p: Principal = Depends(current_principal),
                  session: AsyncSession = Depends(get_session)):
    draft = await draft_or_404(session, p, draft_id)
    if p.role == "creator" and draft.author_id != p.user.id:
        raise HTTPException(403, "Creators can see the history of their own drafts")
    users = await user_names(session, p.org_id)
    versions = (await session.scalars(select(DraftVersion).where(DraftVersion.draft_id == draft.id)
                                      .order_by(DraftVersion.version_no))).all()
    decisions = (await session.scalars(select(WorkflowDecision).where(WorkflowDecision.draft_id == draft.id)
                                       .order_by(WorkflowDecision.created_at))).all()
    finding_decisions = (await session.execute(
        select(FindingDecision, Finding, DraftVersion.version_no)
        .join(Finding, Finding.id == FindingDecision.finding_id)
        .join(DraftVersion, DraftVersion.id == Finding.draft_version_id)
        .where(DraftVersion.draft_id == draft.id).order_by(FindingDecision.created_at)
    )).all()
    events = (await session.scalars(select(AuditEvent).where(
        AuditEvent.org_id == p.org_id, AuditEvent.entity_type == "draft", AuditEvent.entity_id == str(draft.id))
        .order_by(AuditEvent.id))).all()
    return {
        "versions": [{"version_no": v.version_no, "id": str(v.id), "created_at": v.created_at.isoformat(),
                      "author": users.get(v.created_by), "source_type": v.source_type, "text_hash": v.text_hash,
                      "rulebook_version": v.rulebook_version, "facts_version": v.facts_version} for v in versions],
        "decisions": [{"version_no": d.version_no, "decision": d.decision, "reason": d.reason,
                       "claims_reviewed": d.claims_reviewed, "actor": users.get(d.actor_id),
                       "created_at": d.created_at.isoformat()} for d in decisions],
        "finding_decisions": [{"version_no": vno, "action": fd.action, "reason": fd.reason, "actor": users.get(fd.actor_id),
                               "finding": {"id": str(f.id), "lane": f.lane, "message": f.message, "span": f.span_text,
                                           "code": f.rule_code or f.claim_label or f.criterion_code},
                               "created_at": fd.created_at.isoformat()} for fd, f, vno in finding_decisions],
        "audit": [{"id": e.id, "action": e.action, "actor": users.get(e.actor_id) if e.actor_id else None,
                   "payload": e.payload, "created_at": e.created_at.isoformat(), "hash": e.hash,
                   "prev_hash": e.prev_hash} for e in events],
        "chain": await verify_chain(session, p.org_id),
    }
