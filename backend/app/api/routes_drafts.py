import hashlib
import uuid
from typing import Literal

from diff_match_patch import diff_match_patch
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import worker
from app.api.common import draft_or_404, user_names
from app.audit import append_event
from app.config import get_settings
from app.db import get_session
from app.deps import Principal, current_principal, limiter, require_role
from app.extract import MAX_BYTES, MIME, ExtractError, detect_kind, extract_text
from app.models import Draft, DraftVersion, Finding, StoredFile
from app.review import create_version
from app.workflow.state import TransitionError, check_transition

router = APIRouter(prefix="/api", tags=["drafts"])
Channel = Literal["instagram", "x", "linkedin", "email", "product_page", "ad"]


class DraftIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    channel: Channel
    purpose: str = Field(min_length=3, max_length=140)
    text: str = Field(min_length=1, max_length=20000)


class VersionIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


def _rate_limit(p: Principal) -> None:
    if not limiter.hit(f"review:{p.org_id}", get_settings().reviews_per_hour):
        raise HTTPException(429, f"This workspace has reached {get_settings().reviews_per_hour} reviews this hour.")


async def _counts(session: AsyncSession, version_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    if not version_ids:
        return {}
    rows = (await session.execute(
        select(Finding.draft_version_id, Finding.lane, Finding.severity, Finding.status, func.count())
        .where(Finding.draft_version_id.in_(version_ids))
        .group_by(Finding.draft_version_id, Finding.lane, Finding.severity, Finding.status)
    )).all()
    out: dict[uuid.UUID, dict] = {v: {"blocking_open": 0, "claims": 0, "dismissed": 0, "advisory": 0} for v in version_ids}
    for vid, lane, sev, status, n in rows:
        c = out[vid]
        if sev == "blocking" and status in ("open", "accepted", "edited"):
            c["blocking_open"] += n
        if lane == "claims":
            c["claims"] += n
        if status == "dismissed":
            c["dismissed"] += n
        if sev == "advisory":
            c["advisory"] += n
    return out


def draft_out(d: Draft, users: dict, counts: dict | None = None, version_id=None) -> dict:
    return {
        "id": str(d.id), "title": d.title, "channel": d.channel, "purpose": d.purpose, "status": d.status,
        "author": users.get(d.author_id), "current_version_no": d.current_version_no,
        "current_version_id": str(version_id) if version_id else None,
        "created_at": d.created_at.isoformat(), "updated_at": d.updated_at.isoformat(),
        "counts": counts or {"blocking_open": 0, "claims": 0, "dismissed": 0, "advisory": 0},
    }


@router.get("/drafts")
async def list_drafts(status: str | None = None, mine: bool = False, p: Principal = Depends(current_principal),
                      session: AsyncSession = Depends(get_session)):
    q = (select(Draft, DraftVersion.id).outerjoin(
        DraftVersion, (DraftVersion.draft_id == Draft.id) & (DraftVersion.version_no == Draft.current_version_no))
        .where(Draft.org_id == p.org_id).order_by(Draft.updated_at.desc()))
    if status:
        q = q.where(Draft.status.in_(status.split(",")))
    if mine:
        q = q.where(Draft.author_id == p.user.id)
    rows = (await session.execute(q)).all()
    counts = await _counts(session, [vid for _, vid in rows if vid])
    users = await user_names(session, p.org_id)
    return [draft_out(d, users, counts.get(vid), vid) for d, vid in rows]


async def _new_draft(session: AsyncSession, p: Principal, title: str, channel: str, purpose: str, text: str,
                     source_type: str = "paste", file_id=None) -> dict:
    draft = Draft(org_id=p.org_id, title=title.strip(), channel=channel, purpose=purpose.strip(), author_id=p.user.id)
    session.add(draft)
    await session.flush()
    await append_event(session, p.org_id, p.user.id, "draft", draft.id, "draft.created",
                       {"title": draft.title, "channel": channel, "purpose": draft.purpose})
    version = await create_version(session, p.org, draft, p.user, text, source_type, file_id)
    await session.commit()
    worker.wake()
    return {"id": str(draft.id), "version_id": str(version.id), "version_no": version.version_no}


@router.post("/drafts", status_code=201)
async def create_draft(body: DraftIn, p: Principal = Depends(require_role("creator", "admin")),
                       session: AsyncSession = Depends(get_session)):
    _rate_limit(p)
    return await _new_draft(session, p, body.title, body.channel, body.purpose, body.text)


@router.post("/drafts/upload", status_code=201)
async def upload_draft(title: str = Form(...), channel: Channel = Form(...), purpose: str = Form(...),
                       file: UploadFile = File(...), p: Principal = Depends(require_role("creator", "admin")),
                       session: AsyncSession = Depends(get_session)):
    _rate_limit(p)
    if not (3 <= len(purpose.strip()) <= 140):
        raise HTTPException(422, "Purpose line must be 3-140 characters")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Files must be 5 MB or smaller")
    try:
        kind = detect_kind(file.filename or "", data)
        text = extract_text(kind, data)
    except ExtractError as e:
        raise HTTPException(422, str(e)) from e
    stored = StoredFile(org_id=p.org_id, filename=(file.filename or "upload")[:255], mime=MIME[kind],
                        size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), data=data, created_by=p.user.id)
    session.add(stored)
    await session.flush()
    return await _new_draft(session, p, title, channel, purpose, text, kind, stored.id)


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: uuid.UUID, p: Principal = Depends(current_principal),
                    session: AsyncSession = Depends(get_session)):
    draft = await draft_or_404(session, p, draft_id)
    versions = (await session.scalars(select(DraftVersion).where(DraftVersion.draft_id == draft.id)
                                      .order_by(DraftVersion.version_no))).all()
    cur = versions[-1] if versions else None
    users = await user_names(session, p.org_id)
    counts = await _counts(session, [cur.id]) if cur else {}
    out = draft_out(draft, users, counts.get(cur.id) if cur else None, cur.id if cur else None)
    out["versions"] = [{"id": str(v.id), "version_no": v.version_no, "created_at": v.created_at.isoformat(),
                        "source_type": v.source_type, "rulebook_version": v.rulebook_version,
                        "facts_version": v.facts_version} for v in versions]
    out["current_text"] = cur.text if cur else ""
    is_author = draft.author_id == p.user.id
    out["can"] = {
        "edit": p.role == "admin" or (p.role == "creator" and is_author),
        "review": p.role in ("reviewer", "admin"),
    }
    return out


@router.post("/drafts/{draft_id}/versions", status_code=201)
async def new_version(draft_id: uuid.UUID, body: VersionIn, p: Principal = Depends(current_principal),
                      session: AsyncSession = Depends(get_session)):
    draft = await draft_or_404(session, p, draft_id, lock=True)
    try:
        check_transition("new_version", draft.status, p.role, draft.author_id == p.user.id)
    except TransitionError as e:
        raise HTTPException(e.status_code, str(e)) from e
    _rate_limit(p)
    version = await create_version(session, p.org, draft, p.user, body.text)
    await session.commit()
    worker.wake()
    return {"id": str(draft.id), "version_id": str(version.id), "version_no": version.version_no}


@router.get("/drafts/{draft_id}/versions/{n}")
async def get_version(draft_id: uuid.UUID, n: int, p: Principal = Depends(current_principal),
                      session: AsyncSession = Depends(get_session)):
    draft = await draft_or_404(session, p, draft_id)
    v = await session.scalar(select(DraftVersion).where(DraftVersion.draft_id == draft.id, DraftVersion.version_no == n))
    if v is None:
        raise HTTPException(404, "Version not found")
    return {"id": str(v.id), "version_no": v.version_no, "text": v.text, "created_at": v.created_at.isoformat(),
            "source_type": v.source_type, "rulebook_version": v.rulebook_version, "facts_version": v.facts_version}


@router.get("/drafts/{draft_id}/diff")
async def diff(draft_id: uuid.UUID, from_: int = Query(alias="from"), to: int = Query(),
               p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)):
    draft = await draft_or_404(session, p, draft_id)
    texts = dict((await session.execute(select(DraftVersion.version_no, DraftVersion.text)
                                        .where(DraftVersion.draft_id == draft.id))).all())
    a, b = texts.get(from_), texts.get(to)
    if a is None or b is None:
        raise HTTPException(404, "Version not found")
    dmp = diff_match_patch()
    ops = dmp.diff_main(a, b)
    dmp.diff_cleanupSemantic(ops)
    return {"from": from_, "to": to, "ops": [{"op": {-1: "del", 0: "eq", 1: "ins"}[o], "text": t} for o, t in ops]}
