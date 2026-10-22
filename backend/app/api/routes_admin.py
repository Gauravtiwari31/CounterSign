"""Admin: rulebook (copy-on-write versions), evidence library, voice rubric, palette, users, audit."""
import re
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import user_names
from app.audit import append_event, verify_chain
from app.db import get_session
from app.deps import Principal, current_principal, require_role
from app.embeddings import embed
from app.lanes.context import active_clause
from app.lanes.rules.engine import RuleSpec, run_rules, validate_rule
from app.models import RULE_TYPES, AuditEvent, Fact, Organization, PaletteColor, Rule, User, VoiceCriterion

router = APIRouter(prefix="/api", tags=["admin"])
admin_only = require_role("admin")
Severity = Literal["blocking", "warning", "info"]


async def _lock_org(session: AsyncSession, org_id: uuid.UUID) -> Organization:
    return await session.scalar(select(Organization).where(Organization.id == org_id).with_for_update())


# ---------------- rules ----------------

class RuleIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z]{1,3}\d{1,3}$")
    type: Literal[RULE_TYPES]  # type: ignore[valid-type]
    params: dict
    severity: Severity
    channels: list[str] | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str = ""


def rule_out(r: Rule) -> dict:
    return {"id": str(r.id), "code": r.code, "type": r.type, "params": r.params, "severity": r.severity,
            "channels": r.channels, "title": r.title, "description": r.description,
            "introduced_in": r.introduced_in, "retired_in": r.retired_in}


@router.get("/rules")
async def list_rules(p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)):
    rules = (await session.scalars(select(Rule).where(active_clause(Rule, p.org_id, p.org.rulebook_version))
                                   .order_by(Rule.code))).all()
    return {"rulebook_version": p.org.rulebook_version, "rules": [rule_out(r) for r in rules]}


def _validate(body: RuleIn) -> None:
    errors = validate_rule(body.type, body.params)
    if errors:
        raise HTTPException(422, "; ".join(errors))


async def _active_rule(session: AsyncSession, org: Organization, rule_id: uuid.UUID) -> Rule:
    rule = await session.scalar(select(Rule).where(Rule.id == rule_id, active_clause(Rule, org.id, org.rulebook_version)))
    if rule is None:
        raise HTTPException(404, "Rule not found (or already retired)")
    return rule


@router.post("/rules", status_code=201)
async def create_rule(body: RuleIn, p: Principal = Depends(admin_only), session: AsyncSession = Depends(get_session)):
    _validate(body)
    org = await _lock_org(session, p.org_id)
    clash = await session.scalar(select(Rule.id).where(active_clause(Rule, org.id, org.rulebook_version), Rule.code == body.code))
    if clash:
        raise HTTPException(409, f"Rule {body.code} already exists")
    org.rulebook_version += 1
    rule = Rule(org_id=org.id, introduced_in=org.rulebook_version, created_by=p.user.id, **body.model_dump())
    session.add(rule)
    await session.flush()
    await append_event(session, org.id, p.user.id, "rule", rule.id, "rule.created",
                       {"code": rule.code, "rulebook_version": org.rulebook_version})
    await session.commit()
    return rule_out(rule)


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: uuid.UUID, body: RuleIn, p: Principal = Depends(admin_only),
                      session: AsyncSession = Depends(get_session)):
    _validate(body)
    org = await _lock_org(session, p.org_id)
    old = await _active_rule(session, org, rule_id)
    org.rulebook_version += 1
    old.retired_in = org.rulebook_version
    new = Rule(org_id=org.id, introduced_in=org.rulebook_version, created_by=p.user.id, **body.model_dump())
    session.add(new)
    await session.flush()
    await append_event(session, org.id, p.user.id, "rule", new.id, "rule.updated",
                       {"code": new.code, "replaces": str(old.id), "rulebook_version": org.rulebook_version})
    await session.commit()
    return rule_out(new)


@router.delete("/rules/{rule_id}")
async def retire_rule(rule_id: uuid.UUID, p: Principal = Depends(admin_only), session: AsyncSession = Depends(get_session)):
    org = await _lock_org(session, p.org_id)
    old = await _active_rule(session, org, rule_id)
    org.rulebook_version += 1
    old.retired_in = org.rulebook_version
    await append_event(session, org.id, p.user.id, "rule", old.id, "rule.retired",
                       {"code": old.code, "rulebook_version": org.rulebook_version})
    await session.commit()
    return {"ok": True, "rulebook_version": org.rulebook_version}


class RuleTestIn(BaseModel):
    rule: RuleIn
    text: str = Field(max_length=20000)
    channel: str = "instagram"


@router.post("/rules/test")
async def test_rule(body: RuleTestIn, p: Principal = Depends(admin_only)):
    errors = validate_rule(body.rule.type, body.rule.params)
    if errors:
        return {"ok": False, "errors": errors, "hits": []}
    spec = RuleSpec(**body.rule.model_dump(), id=None)
    hits = run_rules(body.text, body.channel, [spec])
    return {"ok": True, "errors": [], "hits": [
        {"start": h.start, "end": h.end, "text": h.span_text, "message": h.message, "replacement": h.replacement}
        for h in hits]}


# ---------------- facts ----------------

class FactIn(BaseModel):
    code: str = Field(pattern=r"^(?:[A-Z]-)?F-?\d{1,3}$")
    statement: str = Field(min_length=5, max_length=1000)
    source_document: str = ""
    source_locator: str = ""
    owner: str = ""
    scope_products: list[str] = []
    scope_channels: list[str] = []
    scope_regions: list[str] = []
    valid_from: date | None = None
    valid_to: date | None = None
    superseded_by: uuid.UUID | None = None

    @field_validator("valid_to")
    @classmethod
    def _order(cls, v, info):
        vf = info.data.get("valid_from")
        if v and vf and v < vf:
            raise ValueError("valid_to is before valid_from")
        return v


def fact_out(f: Fact, codes: dict) -> dict:
    today = date.today()
    status = ("superseded" if f.superseded_by else "expired" if f.valid_to and f.valid_to < today
              else "expiring_soon" if f.valid_to and (f.valid_to - today).days <= 30 else "valid")
    return {"id": str(f.id), "code": f.code, "statement": f.statement, "source_document": f.source_document,
            "source_locator": f.source_locator, "owner": f.owner, "scope_products": f.scope_products,
            "scope_channels": f.scope_channels, "scope_regions": f.scope_regions,
            "valid_from": f.valid_from.isoformat() if f.valid_from else None,
            "valid_to": f.valid_to.isoformat() if f.valid_to else None,
            "superseded_by": str(f.superseded_by) if f.superseded_by else None,
            "superseded_by_code": codes.get(f.superseded_by), "status": status, "introduced_in": f.introduced_in}


async def _fact_codes(session: AsyncSession, org_id: uuid.UUID) -> dict:
    return dict((await session.execute(select(Fact.id, Fact.code).where(Fact.org_id == org_id))).all())


@router.get("/facts")
async def list_facts(p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)):
    facts = (await session.scalars(select(Fact).where(active_clause(Fact, p.org_id, p.org.facts_version))
                                   .order_by(Fact.code))).all()
    codes = await _fact_codes(session, p.org_id)
    return {"facts_version": p.org.facts_version, "facts": [fact_out(f, codes) for f in facts]}


async def _check_superseded_by(session: AsyncSession, org_id: uuid.UUID, fid: uuid.UUID | None) -> None:
    if fid and not await session.scalar(select(Fact.id).where(Fact.id == fid, Fact.org_id == org_id)):
        raise HTTPException(422, "superseded_by must be a fact in this workspace")


def _new_fact(org: Organization, body: FactIn, user_id: uuid.UUID) -> Fact:
    return Fact(org_id=org.id, introduced_in=org.facts_version, created_by=user_id,
                embedding=embed([body.statement])[0], **body.model_dump())


@router.post("/facts", status_code=201)
async def create_fact(body: FactIn, p: Principal = Depends(admin_only), session: AsyncSession = Depends(get_session)):
    await _check_superseded_by(session, p.org_id, body.superseded_by)
    org = await _lock_org(session, p.org_id)
    org.facts_version += 1
    fact = _new_fact(org, body, p.user.id)
    session.add(fact)
    await session.flush()
    await append_event(session, org.id, p.user.id, "fact", fact.id, "fact.created",
                       {"code": fact.code, "facts_version": org.facts_version})
    await session.commit()
    return fact_out(fact, await _fact_codes(session, org.id))


@router.put("/facts/{fact_id}")
async def update_fact(fact_id: uuid.UUID, body: FactIn, p: Principal = Depends(admin_only),
                      session: AsyncSession = Depends(get_session)):
    await _check_superseded_by(session, p.org_id, body.superseded_by)
    org = await _lock_org(session, p.org_id)
    old = await session.scalar(select(Fact).where(Fact.id == fact_id, active_clause(Fact, org.id, org.facts_version)))
    if old is None:
        raise HTTPException(404, "Fact not found")
    org.facts_version += 1
    old.retired_in = org.facts_version
    new = _new_fact(org, body, p.user.id)
    session.add(new)
    await session.flush()
    await append_event(session, org.id, p.user.id, "fact", new.id, "fact.updated",
                       {"code": new.code, "replaces": str(old.id), "facts_version": org.facts_version})
    await session.commit()
    return fact_out(new, await _fact_codes(session, org.id))


@router.delete("/facts/{fact_id}")
async def retire_fact(fact_id: uuid.UUID, p: Principal = Depends(admin_only), session: AsyncSession = Depends(get_session)):
    org = await _lock_org(session, p.org_id)
    old = await session.scalar(select(Fact).where(Fact.id == fact_id, active_clause(Fact, org.id, org.facts_version)))
    if old is None:
        raise HTTPException(404, "Fact not found")
    org.facts_version += 1
    old.retired_in = org.facts_version
    await append_event(session, org.id, p.user.id, "fact", old.id, "fact.retired",
                       {"code": old.code, "facts_version": org.facts_version})
    await session.commit()
    return {"ok": True, "facts_version": org.facts_version}


# ---------------- voice rubric ----------------

class CriterionIn(BaseModel):
    code: str = Field(pattern=r"^V\d{1,2}$")
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    good_examples: list[str] = []
    bad_examples: list[str] = []


def criterion_out(c: VoiceCriterion) -> dict:
    return {"id": str(c.id), "code": c.code, "title": c.title, "description": c.description,
            "good_examples": c.good_examples, "bad_examples": c.bad_examples}


@router.get("/voice-criteria")
async def list_criteria(p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)):
    rows = (await session.scalars(select(VoiceCriterion).where(
        active_clause(VoiceCriterion, p.org_id, p.org.rulebook_version)).order_by(VoiceCriterion.code))).all()
    return [criterion_out(c) for c in rows]


@router.post("/voice-criteria", status_code=201)
async def create_criterion(body: CriterionIn, p: Principal = Depends(admin_only),
                           session: AsyncSession = Depends(get_session)):
    org = await _lock_org(session, p.org_id)
    org.rulebook_version += 1
    c = VoiceCriterion(org_id=org.id, introduced_in=org.rulebook_version, **body.model_dump())
    session.add(c)
    await session.flush()
    await append_event(session, org.id, p.user.id, "voice", c.id, "voice.created", {"code": c.code})
    await session.commit()
    return criterion_out(c)


@router.put("/voice-criteria/{criterion_id}")
async def update_criterion(criterion_id: uuid.UUID, body: CriterionIn, p: Principal = Depends(admin_only),
                           session: AsyncSession = Depends(get_session)):
    org = await _lock_org(session, p.org_id)
    old = await session.scalar(select(VoiceCriterion).where(
        VoiceCriterion.id == criterion_id, active_clause(VoiceCriterion, org.id, org.rulebook_version)))
    if old is None:
        raise HTTPException(404, "Criterion not found")
    org.rulebook_version += 1
    old.retired_in = org.rulebook_version
    new = VoiceCriterion(org_id=org.id, introduced_in=org.rulebook_version, **body.model_dump())
    session.add(new)
    await session.flush()
    await append_event(session, org.id, p.user.id, "voice", new.id, "voice.updated", {"code": new.code})
    await session.commit()
    return criterion_out(new)


# ---------------- palette ----------------

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ColorIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    hex: str
    role: Literal["text", "background", "accent"]

    @field_validator("hex")
    @classmethod
    def _hex(cls, v):
        if not HEX.match(v):
            raise ValueError("Use a 6-digit hex colour like #1B1F1D")
        return v.upper()


def _luminance(hex_: str) -> float:
    def ch(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def contrast_matrix(colors: list[PaletteColor]) -> list[dict]:
    fgs = [c for c in colors if c.role in ("text", "accent")]
    bgs = [c for c in colors if c.role in ("background", "accent")]
    out = []
    for fg in fgs:
        for bg in bgs:
            if fg.id == bg.id:
                continue
            r = contrast_ratio(fg.hex, bg.hex)
            out.append({"foreground": fg.name, "foreground_hex": fg.hex, "background": bg.name, "background_hex": bg.hex,
                        "ratio": round(r, 2), "aa_normal": r >= 4.5, "aa_large": r >= 3.0, "aaa_normal": r >= 7.0})
    return out


@router.get("/palette")
async def get_palette(p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)):
    colors = (await session.scalars(select(PaletteColor).where(PaletteColor.org_id == p.org_id)
                                    .order_by(PaletteColor.role, PaletteColor.name))).all()
    return {"colors": [{"name": c.name, "hex": c.hex, "role": c.role} for c in colors],
            "matrix": contrast_matrix(list(colors))}


@router.put("/palette")
async def put_palette(body: list[ColorIn], p: Principal = Depends(admin_only), session: AsyncSession = Depends(get_session)):
    await session.execute(PaletteColor.__table__.delete().where(PaletteColor.org_id == p.org_id))
    session.add_all([PaletteColor(org_id=p.org_id, **c.model_dump()) for c in body])
    await append_event(session, p.org_id, p.user.id, "palette", p.org_id, "palette.updated", {"colors": len(body)})
    await session.commit()
    return await get_palette(p, session)


# ---------------- users & audit ----------------

@router.get("/users")
async def list_users(p: Principal = Depends(admin_only), session: AsyncSession = Depends(get_session)):
    users = (await session.scalars(select(User).where(User.org_id == p.org_id).order_by(User.role))).all()
    return [{"id": str(u.id), "name": u.name, "email": u.email, "role": u.role} for u in users]


@router.get("/audit")
async def audit_log(entity: str | None = None, limit: int = 200, p: Principal = Depends(require_role("reviewer", "admin")),
                    session: AsyncSession = Depends(get_session)):
    q = select(AuditEvent).where(AuditEvent.org_id == p.org_id)
    if entity:
        q = q.where(AuditEvent.entity_id == entity)
    events = (await session.scalars(q.order_by(AuditEvent.id.desc()).limit(min(limit, 1000)))).all()
    users = await user_names(session, p.org_id)
    return {"chain": await verify_chain(session, p.org_id),
            "events": [{"id": e.id, "entity_type": e.entity_type, "entity_id": e.entity_id, "action": e.action,
                        "actor": users.get(e.actor_id) if e.actor_id else None, "payload": e.payload,
                        "created_at": e.created_at.isoformat(), "hash": e.hash} for e in events]}

