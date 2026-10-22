import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import worker
from app.api.common import finding_or_404, version_or_404
from app.audit import append_event
from app.db import get_session
from app.deps import Principal, current_principal
from app.models import Finding, FindingDecision, ReviewJob
from app.review import retry_ai
from app.schemas.finding import FindingOut, sort_key
from app.workflow.state import TransitionError, check_finding_action

router = APIRouter(prefix="/api", tags=["review"])


@router.get("/versions/{version_id}/review")
async def get_review(version_id: uuid.UUID, p: Principal = Depends(current_principal),
                     session: AsyncSession = Depends(get_session)):
    version, draft = await version_or_404(session, p, version_id)
    job = await session.scalar(select(ReviewJob).where(ReviewJob.draft_version_id == version.id))
    findings = sorted((await session.scalars(select(Finding).where(Finding.draft_version_id == version.id))).all(),
                      key=sort_key)
    # decisions on this finding or on the earlier finding it was carried over from
    ids = [f.id for f in findings] + [f.carried_from for f in findings if f.carried_from]
    decisions: dict = {}
    for d in (await session.scalars(select(FindingDecision).where(FindingDecision.finding_id.in_(ids))
                                    .order_by(FindingDecision.created_at))).all():
        decisions.setdefault(d.finding_id, []).append({"action": d.action, "reason": d.reason, "role": d.actor_role})

    def out(f: Finding) -> dict:
        data = FindingOut.from_row(f).model_dump(mode="json")
        data["decisions"] = decisions.get(f.carried_from, []) + decisions.get(f.id, [])
        return data

    return {
        "version": {"id": str(version.id), "version_no": version.version_no, "text": version.text,
                    "rulebook_version": version.rulebook_version, "facts_version": version.facts_version},
        "job": {"status": job.status, "lane_status": job.lane_status, "timings": job.timings,
                "ai_degraded": job.ai_degraded, "error": job.error} if job else None,
        "findings": [out(f) for f in findings],
    }


@router.post("/versions/{version_id}/retry-ai")
async def retry(version_id: uuid.UUID, p: Principal = Depends(current_principal),
                session: AsyncSession = Depends(get_session)):
    version, draft = await version_or_404(session, p, version_id)
    if draft.status in ("approved", "rejected", "in_review"):
        raise HTTPException(409, "AI checks can only be re-run before the draft goes to review")
    if p.role == "creator" and draft.author_id != p.user.id:
        raise HTTPException(403, "Creators can only act on their own drafts")
    job = await retry_ai(session, version)
    await append_event(session, p.org_id, p.user.id, "draft", draft.id, "review.retry_ai",
                       {"version_no": version.version_no})
    await session.commit()
    worker.wake()
    return {"status": job.status}


class DecisionIn(BaseModel):
    action: Literal["accept", "edit", "dismiss", "override", "reopen"]
    reason: str | None = Field(None, max_length=1000)
    edited_text: str | None = Field(None, max_length=5000)


@router.post("/findings/{finding_id}/decision")
async def finding_decision(finding_id: uuid.UUID, body: DecisionIn, p: Principal = Depends(current_principal),
                           session: AsyncSession = Depends(get_session)):
    finding, version, draft = await finding_or_404(session, p, finding_id)
    if version.version_no != draft.current_version_no:
        raise HTTPException(409, "This finding belongs to an older version")
    try:
        new_status = check_finding_action(body.action, p.role, draft.author_id == p.user.id, draft.status,
                                          finding.severity, body.reason)
    except TransitionError as e:
        raise HTTPException(e.status_code, str(e)) from e
    old_status = finding.status
    finding.status = new_status
    session.add(FindingDecision(finding_id=finding.id, actor_id=p.user.id, actor_role=p.role, action=body.action,
                                reason=body.reason, edited_text=body.edited_text))
    await append_event(session, p.org_id, p.user.id, "draft", draft.id, f"finding.{body.action}", {
        "finding_id": str(finding.id), "version_no": version.version_no, "lane": finding.lane,
        "code": finding.rule_code or finding.claim_label or finding.criterion_code, "from": old_status,
        "to": new_status, "reason": body.reason,
    })
    await session.commit()
    return FindingOut.from_row(finding).model_dump(mode="json")
