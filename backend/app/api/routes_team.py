"""Team management for real workspaces: invite links, roles, removal, password reset links.

Links are shown to the admin to share however they like; nothing is emailed. Only a SHA-256 of each token is
stored, so a database read cannot be turned into a working link.
"""
import hashlib
import secrets
import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes_auth import MIN_PASSWORD, email_taken, normal_email
from app.audit import append_event
from app.config import get_settings
from app.db import get_session
from app.deps import Principal, client_ip, limiter, require_role
from app.models import Invite, Organization, User, utcnow
from app.security import hash_password, issue_token, set_session_cookie

router = APIRouter(prefix="/api", tags=["team"])
admin_only = require_role("admin")
Role = Literal["creator", "reviewer", "admin"]


class InviteIn(BaseModel):
    email: str = Field(max_length=200)
    name: str = Field(min_length=1, max_length=120)
    role: Role


class RoleIn(BaseModel):
    role: Role


class AcceptIn(BaseModel):
    password: str = Field(min_length=MIN_PASSWORD, max_length=200)
    name: str | None = Field(None, max_length=120)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def _new_link(session: AsyncSession, p: Principal, *, email: str, name: str, role: str,
                    user_id: uuid.UUID | None = None) -> tuple[Invite, str]:
    # one live link per person: a new link replaces any earlier unused one
    old = (await session.scalars(select(Invite).where(
        Invite.org_id == p.org_id, Invite.email == email, Invite.accepted_at.is_(None)))).all()
    for inv in old:
        await session.delete(inv)
    token = secrets.token_urlsafe(32)
    inv = Invite(org_id=p.org_id, email=email, name=name, role=role, token_hash=_hash(token), user_id=user_id,
                 created_by=p.user.id, expires_at=utcnow() + timedelta(days=get_settings().invite_ttl_days))
    session.add(inv)
    await session.flush()
    return inv, token


def _invite_out(inv: Invite) -> dict:
    return {"id": str(inv.id), "email": inv.email, "name": inv.name, "role": inv.role,
            "kind": "reset" if inv.user_id else "join", "expires_at": inv.expires_at.isoformat(),
            "expired": inv.expires_at < utcnow()}


async def _user_or_404(session: AsyncSession, p: Principal, user_id: uuid.UUID) -> User:
    user = await session.scalar(select(User).where(User.id == user_id, User.org_id == p.org_id).with_for_update())
    if user is None or user.deactivated_at is not None:
        raise HTTPException(404, "Person not found")
    return user


async def _other_admins(session: AsyncSession, p: Principal, user: User) -> int:
    return await session.scalar(select(func.count()).select_from(User).where(
        User.org_id == p.org_id, User.role == "admin", User.deactivated_at.is_(None), User.id != user.id))


@router.get("/team")
async def team(p: Principal = Depends(admin_only), session: AsyncSession = Depends(get_session)):
    users = (await session.scalars(select(User).where(User.org_id == p.org_id).order_by(User.created_at))).all()
    invites = (await session.scalars(select(Invite).where(
        Invite.org_id == p.org_id, Invite.accepted_at.is_(None), Invite.user_id.is_(None))
        .order_by(Invite.created_at.desc()))).all()
    return {
        "users": [{"id": str(u.id), "name": u.name, "email": u.email, "role": u.role, "is_you": u.id == p.user.id,
                   "active": u.deactivated_at is None, "has_password": bool(u.password_hash)} for u in users],
        "invites": [_invite_out(i) for i in invites],
    }


@router.post("/team/invites", status_code=201)
async def invite(body: InviteIn, p: Principal = Depends(admin_only), session: AsyncSession = Depends(get_session)):
    if p.org.is_sandbox:
        raise HTTPException(403, "Demo sandboxes cannot invite people")
    email = normal_email(body.email)
    if await email_taken(session, email):
        raise HTTPException(409, "This email already has an account")
    inv, token = await _new_link(session, p, email=email, name=body.name.strip(), role=body.role)
    await append_event(session, p.org_id, p.user.id, "invite", inv.id, "team.invited", {"email": email, "role": body.role})
    await session.commit()
    return {"invite": _invite_out(inv), "token": token}


@router.delete("/team/invites/{invite_id}")
async def revoke(invite_id: uuid.UUID, p: Principal = Depends(admin_only), session: AsyncSession = Depends(get_session)):
    inv = await session.scalar(select(Invite).where(Invite.id == invite_id, Invite.org_id == p.org_id,
                                                    Invite.accepted_at.is_(None)))
    if inv is None:
        raise HTTPException(404, "Invite not found")
    await append_event(session, p.org_id, p.user.id, "invite", inv.id, "team.invite_revoked", {"email": inv.email})
    await session.delete(inv)
    await session.commit()
    return {"ok": True}


@router.put("/team/users/{user_id}/role")
async def change_role(user_id: uuid.UUID, body: RoleIn, p: Principal = Depends(admin_only),
                      session: AsyncSession = Depends(get_session)):
    user = await _user_or_404(session, p, user_id)
    if user.role == "admin" and body.role != "admin" and not await _other_admins(session, p, user):
        raise HTTPException(409, "A workspace needs at least one admin. Make someone else admin first.")
    old, user.role = user.role, body.role
    await append_event(session, p.org_id, p.user.id, "user", user.id, "team.role_changed", {"from": old, "to": body.role})
    await session.commit()
    return {"ok": True, "role": user.role}


@router.delete("/team/users/{user_id}")
async def remove(user_id: uuid.UUID, p: Principal = Depends(admin_only), session: AsyncSession = Depends(get_session)):
    user = await _user_or_404(session, p, user_id)
    if user.role == "admin" and not await _other_admins(session, p, user):
        raise HTTPException(409, "A workspace needs at least one admin. Make someone else admin first.")
    user.deactivated_at = utcnow()
    await append_event(session, p.org_id, p.user.id, "user", user.id, "team.removed", {"email": user.email})
    await session.commit()
    return {"ok": True}


@router.post("/team/users/{user_id}/reset-link", status_code=201)
async def reset_link(user_id: uuid.UUID, p: Principal = Depends(admin_only), session: AsyncSession = Depends(get_session)):
    user = await _user_or_404(session, p, user_id)
    inv, token = await _new_link(session, p, email=user.email, name=user.name, role=user.role, user_id=user.id)
    await append_event(session, p.org_id, p.user.id, "user", user.id, "team.reset_link", {"email": user.email})
    await session.commit()
    return {"invite": _invite_out(inv), "token": token}


async def _live_invite(session: AsyncSession, token: str, lock: bool = False) -> Invite:
    q = select(Invite).where(Invite.token_hash == _hash(token), Invite.accepted_at.is_(None))
    inv = await session.scalar(q.with_for_update() if lock else q)
    if inv is None:
        raise HTTPException(404, "This link is not valid. Ask your admin for a new one.")
    if inv.expires_at < utcnow():
        raise HTTPException(410, "This link has expired. Ask your admin for a new one.")
    return inv


@router.get("/invites/{token}")
async def invite_info(token: str, session: AsyncSession = Depends(get_session)):
    inv = await _live_invite(session, token)
    org = await session.get(Organization, inv.org_id)
    return {"email": inv.email, "name": inv.name, "role": inv.role, "org_name": org.name,
            "kind": "reset" if inv.user_id else "join"}


@router.post("/invites/{token}/accept")
async def accept(token: str, body: AcceptIn, request: Request, response: Response,
                 session: AsyncSession = Depends(get_session)):
    if not limiter.hit(f"invite:{client_ip(request)}", 30, window_s=600):
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")
    inv = await _live_invite(session, token, lock=True)
    if inv.user_id:
        user = await session.get(User, inv.user_id)
        if user is None or user.deactivated_at is not None:
            raise HTTPException(404, "This account was removed. Ask your admin.")
        user.password_hash = hash_password(body.password)
        action = "user.password_set"
    else:
        if await email_taken(session, inv.email):
            raise HTTPException(409, "This email already has an account. Sign in instead.")
        user = User(org_id=inv.org_id, email=inv.email, name=(body.name or inv.name).strip(), role=inv.role,
                    password_hash=hash_password(body.password))
        session.add(user)
        await session.flush()
        action = "user.joined"
    inv.accepted_at = utcnow()
    await append_event(session, inv.org_id, user.id, "user", user.id, action, {"role": user.role, "via": "invite"})
    await session.commit()
    set_session_cookie(response, issue_token(user.id, user.org_id, user.role))
    return {"ok": True, "role": user.role}
