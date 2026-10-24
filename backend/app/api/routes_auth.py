import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_event
from app.config import get_settings
from app.db import get_session
from app.deps import Principal, client_ip, current_principal, limiter
from app.models import Organization, User
from app.security import COOKIE_NAME, hash_password, issue_token, set_session_cookie, verify_password

router = APIRouter(prefix="/api", tags=["auth"])
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8


class LoginIn(BaseModel):
    email: str
    password: str
    org_slug: str | None = None  # optional: only needed if one email belongs to several workspaces


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=200)
    password: str = Field(min_length=MIN_PASSWORD, max_length=200)
    company: str = Field(min_length=1, max_length=200)


def me_payload(p: Principal) -> dict:
    return {
        "user": {"id": str(p.user.id), "name": p.user.name, "email": p.user.email, "role": p.user.role},
        "org": {"id": str(p.org.id), "name": p.org.name, "slug": p.org.slug, "is_sandbox": p.org.is_sandbox,
                "rulebook_version": p.org.rulebook_version, "facts_version": p.org.facts_version,
                "expires_at": p.org.expires_at.isoformat() if p.org.expires_at else None},
    }


def normal_email(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL.match(email):
        raise HTTPException(422, "Enter a valid email address")
    return email


async def email_taken(session: AsyncSession, email: str) -> bool:
    """One active account per email across real workspaces, so login needs only email and password."""
    return bool(await session.scalar(
        select(User.id).join(Organization, Organization.id == User.org_id)
        .where(User.email == email, User.deactivated_at.is_(None), Organization.is_sandbox.is_(False)).limit(1)))


def slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "workspace"
    return f"{base}-{secrets.token_hex(3)}"


@router.post("/auth/login")
async def login(body: LoginIn, request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    if not limiter.hit(f"login:{client_ip(request)}", 30, window_s=600):
        raise HTTPException(429, "Too many sign-in attempts. Try again in a few minutes.")
    q = (select(User).join(Organization, Organization.id == User.org_id)
         .where(User.email == body.email.lower().strip(), User.deactivated_at.is_(None)))
    q = q.where(Organization.slug == body.org_slug) if body.org_slug else q.where(Organization.is_sandbox.is_(False))
    user = await session.scalar(q.order_by(User.created_at).limit(1))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password")
    set_session_cookie(response, issue_token(user.id, user.org_id, user.role))
    return {"ok": True, "role": user.role}


@router.post("/auth/signup", status_code=201)
async def signup(body: SignupIn, request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    """Create a company workspace; the person who signs up becomes its first Admin."""
    if not limiter.hit(f"signup:{client_ip(request)}", get_settings().signups_per_hour_per_ip):
        raise HTTPException(429, "Too many sign-ups from this network. Try again later.")
    email = normal_email(body.email)
    if await email_taken(session, email):
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    org = Organization(name=body.company.strip(), slug=slugify(body.company), is_sandbox=False)
    session.add(org)
    await session.flush()
    user = User(org_id=org.id, email=email, name=body.name.strip(), role="admin", password_hash=hash_password(body.password))
    session.add(user)
    await session.flush()
    await append_event(session, org.id, user.id, "organization", org.id, "organization.created", {"signup": True})
    await append_event(session, org.id, user.id, "user", user.id, "user.joined", {"role": "admin", "via": "signup"})
    await session.commit()
    set_session_cookie(response, issue_token(user.id, org.id, user.role))
    return {"ok": True, "role": user.role}


@router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def me(p: Principal = Depends(current_principal)):
    return me_payload(p)
