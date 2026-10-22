import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import Principal
from app.models import Draft, DraftVersion, Finding, User
from app.workflow.state import TransitionError


async def draft_or_404(session: AsyncSession, p: Principal, draft_id: uuid.UUID, *, lock: bool = False) -> Draft:
    q = select(Draft).where(Draft.id == draft_id, Draft.org_id == p.org_id)
    if lock:
        q = q.with_for_update()
    draft = await session.scalar(q)
    if draft is None:
        raise HTTPException(404, "Draft not found")
    return draft


async def version_or_404(session: AsyncSession, p: Principal, version_id: uuid.UUID) -> tuple[DraftVersion, Draft]:
    row = (await session.execute(
        select(DraftVersion, Draft).join(Draft, Draft.id == DraftVersion.draft_id)
        .where(DraftVersion.id == version_id, Draft.org_id == p.org_id)
    )).first()
    if row is None:
        raise HTTPException(404, "Version not found")
    return row[0], row[1]


async def finding_or_404(session: AsyncSession, p: Principal, finding_id: uuid.UUID) -> tuple[Finding, DraftVersion, Draft]:
    row = (await session.execute(
        select(Finding, DraftVersion, Draft)
        .join(DraftVersion, DraftVersion.id == Finding.draft_version_id)
        .join(Draft, Draft.id == DraftVersion.draft_id)
        .where(Finding.id == finding_id, Draft.org_id == p.org_id)
        .with_for_update(of=Finding)
    )).first()
    if row is None:
        raise HTTPException(404, "Finding not found")
    return row[0], row[1], row[2]


async def current_version(session: AsyncSession, draft: Draft) -> DraftVersion | None:
    return await session.scalar(select(DraftVersion).where(
        DraftVersion.draft_id == draft.id, DraftVersion.version_no == draft.current_version_no))


async def user_names(session: AsyncSession, org_id: uuid.UUID) -> dict[uuid.UUID, dict]:
    users = (await session.scalars(select(User).where(User.org_id == org_id))).all()
    return {u.id: {"id": str(u.id), "name": u.name, "role": u.role} for u in users}


def raise_transition(e: TransitionError):
    raise HTTPException(e.status_code, str(e))
