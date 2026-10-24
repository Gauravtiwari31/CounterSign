from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_event
from app.config import get_settings
from app.db import get_session
from app.deps import Principal, client_ip, current_principal, limiter
from app.models import User
from app.security import issue_token, set_session_cookie
from app.seed.loader import load_brand
from app.seed.sandbox import DEMO_BRAND, claim_sandbox


def demo_enabled() -> None:
    """The per-visitor sandbox flow is off unless DEMO_SANDBOXES=true (the test suite turns it on)."""
    if not get_settings().demo_sandboxes:
        raise HTTPException(404, "Not found")


router = APIRouter(prefix="/api/demo", tags=["demo"], dependencies=[Depends(demo_enabled)])


class RoleIn(BaseModel):
    role: Literal["creator", "reviewer", "admin"]


@router.post("/session")
async def demo_session(body: RoleIn, request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    if not limiter.hit(f"demo:{client_ip(request)}", get_settings().demo_sessions_per_hour_per_ip):
        raise HTTPException(429, "Too many demo sandboxes from this network. Try again in an hour.")
    org = await claim_sandbox(session)
    user = await session.scalar(select(User).where(User.org_id == org.id, User.role == body.role))
    await append_event(session, org.id, user.id, "organization", org.id, "sandbox.claimed", {"role": body.role})
    await session.commit()
    set_session_cookie(response, issue_token(user.id, org.id, user.role))
    return {"ok": True, "org": org.slug, "role": body.role}


@router.post("/switch-role")
async def switch_role(body: RoleIn, response: Response, p: Principal = Depends(current_principal),
                      session: AsyncSession = Depends(get_session)):
    if not p.org.is_sandbox:
        raise HTTPException(403, "Role switching is only available in demo sandboxes")
    user = await session.scalar(select(User).where(User.org_id == p.org_id, User.role == body.role))
    if user is None:
        raise HTTPException(404, "No user with that role in this sandbox")
    await append_event(session, p.org_id, user.id, "organization", p.org_id, "sandbox.role_switched",
                       {"from": p.role, "to": body.role})
    await session.commit()
    set_session_cookie(response, issue_token(user.id, p.org_id, user.role))
    return {"ok": True, "role": body.role}


@router.get("/sample")
async def sample(p: Principal = Depends(current_principal)):
    return load_brand(DEMO_BRAND)["sample"]
