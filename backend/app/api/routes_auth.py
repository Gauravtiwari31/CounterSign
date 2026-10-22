from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import Principal, current_principal
from app.models import Organization, User
from app.security import COOKIE_NAME, issue_token, set_session_cookie, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


class LoginIn(BaseModel):
    org_slug: str
    email: str
    password: str


def me_payload(p: Principal) -> dict:
    return {
        "user": {"id": str(p.user.id), "name": p.user.name, "email": p.user.email, "role": p.user.role},
        "org": {"id": str(p.org.id), "name": p.org.name, "slug": p.org.slug, "is_sandbox": p.org.is_sandbox,
                "rulebook_version": p.org.rulebook_version, "facts_version": p.org.facts_version,
                "expires_at": p.org.expires_at.isoformat() if p.org.expires_at else None},
    }


@router.post("/auth/login")
async def login(body: LoginIn, response: Response, session: AsyncSession = Depends(get_session)):
    user = await session.scalar(select(User).join(Organization, Organization.id == User.org_id).where(
        Organization.slug == body.org_slug, User.email == body.email.lower().strip()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong workspace, email or password")
    set_session_cookie(response, issue_token(user.id, user.org_id, user.role))
    return {"ok": True}


@router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def me(p: Principal = Depends(current_principal)):
    return me_payload(p)
