"""Per-visitor demo sandboxes.

Each visitor gets a private copy of Verdant Skin with drafts in every state. Sandboxes are pre-built into a small
pool by the worker so a judge's first click is instant; the shared LLM cache makes every later build cheap.
"""
import logging
import secrets
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_event
from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    AuditEvent,
    Comment,
    Draft,
    Finding,
    FindingDecision,
    Organization,
    ReviewJob,
    User,
    WorkflowDecision,
    utcnow,
)
from app.review import create_version, run_ai_lanes
from app.seed.loader import create_org, load_brand

log = logging.getLogger("countersign.sandbox")
DEMO_BRAND = "verdant_skin"
SEED_REASON = "Seed data: reviewer checked this against the evidence library."


def current_brand_key() -> str:
    b = load_brand(DEMO_BRAND)
    return f"{b['key']}@{b['seed_version']}"


async def _seed_drafts(session: AsyncSession, org: Organization, users: dict) -> None:
    brand = load_brand(DEMO_BRAND)
    for spec in brand.get("drafts", []):
        author = users[spec.get("author", "creator")]
        draft = Draft(org_id=org.id, title=spec["title"], channel=spec["channel"], purpose=spec["purpose"],
                      author_id=author.id, status="draft")
        session.add(draft)
        await session.flush()
        await append_event(session, org.id, author.id, "draft", draft.id, "draft.created",
                           {"title": draft.title, "channel": draft.channel, "seed": True})
        version = None
        for text in spec["versions"]:
            version = await create_version(session, org, draft, author, text, inline=True)
            await session.commit()
            job = await session.scalar(select(ReviewJob).where(ReviewJob.draft_version_id == version.id))
            await run_ai_lanes(session, job)

        final = spec.get("final_status", "checked")
        if final in ("in_review", "approved"):
            # the seeded history must satisfy the same guards a real user meets
            findings = (await session.scalars(select(Finding).where(
                Finding.draft_version_id == version.id, Finding.severity == "blocking"))).all()
            reviewer = users["reviewer"]
            for f in findings:
                if f.status == "open":
                    f.status = "overridden"
                    session.add(FindingDecision(finding_id=f.id, actor_id=reviewer.id, actor_role="reviewer",
                                                action="override", reason=SEED_REASON))
        for step in spec.get("flow", []):
            actor = users[step["by"]]
            session.add(WorkflowDecision(draft_id=draft.id, version_no=draft.current_version_no, actor_id=actor.id,
                                         decision=step["decision"], reason=step.get("reason"),
                                         claims_reviewed=step.get("claims_reviewed", False)))
            await append_event(session, org.id, actor.id, "draft", draft.id, f"workflow.{step['decision']}",
                               {"version_no": draft.current_version_no, "reason": step.get("reason"), "seed": True})
        for c in spec.get("comments", []):
            session.add(Comment(draft_id=draft.id, version_no=draft.current_version_no, author_id=users[c["by"]].id,
                                body=c["body"]))
        draft.status = final
        await session.commit()


async def build_sandbox() -> Organization:
    async with SessionLocal() as session:
        org, users = await create_org(session, load_brand(DEMO_BRAND), slug=f"sandbox-{secrets.token_hex(6)}",
                                      is_sandbox=True)
        await session.commit()
        await _seed_drafts(session, org, users)
        await session.commit()
        return org


async def claim_sandbox(session: AsyncSession) -> Organization:
    ttl = timedelta(hours=get_settings().sandbox_ttl_hours)
    org = await session.scalar(
        select(Organization)
        .where(Organization.is_sandbox, Organization.claimed_at.is_(None), Organization.brand_key == current_brand_key())
        .order_by(Organization.created_at).limit(1).with_for_update(skip_locked=True)
    )
    if org is None:
        built = await build_sandbox()
        org = await session.get(Organization, built.id)
    org.claimed_at = utcnow()
    org.expires_at = org.claimed_at + ttl
    await session.flush()
    return org


async def purge_expired(session: AsyncSession) -> int:
    expired = (await session.scalars(select(Organization.id).where(
        Organization.is_sandbox, Organization.expires_at.is_not(None), Organization.expires_at < utcnow()))).all()
    stale_pool = (await session.scalars(select(Organization.id).where(
        Organization.is_sandbox, Organization.claimed_at.is_(None), Organization.brand_key != current_brand_key()))).all()
    if stale_pool:
        # old seed version: expire now so the audit guard allows the purge
        await session.execute(update(Organization).where(Organization.id.in_(stale_pool))
                              .values(expires_at=utcnow() - timedelta(seconds=1)))
        await session.commit()
    ids = list(expired) + list(stale_pool)
    for org_id in ids:
        await session.execute(delete(AuditEvent).where(AuditEvent.org_id == org_id))
        await session.execute(delete(Organization).where(Organization.id == org_id))
    await session.commit()
    return len(ids)


async def housekeeping() -> None:
    async with SessionLocal() as session:
        purged = await purge_expired(session)
        if purged:
            log.info("purged %d expired sandboxes", purged)
        ready = len((await session.scalars(select(Organization.id).where(
            Organization.is_sandbox, Organization.claimed_at.is_(None),
            Organization.brand_key == current_brand_key()))).all())
    await ensure_demo_company()
    if not get_settings().demo_sandboxes:
        return
    for _ in range(max(0, get_settings().sandbox_pool_size - ready)):
        await build_sandbox()


DEMO_SLUG = "verdant-skin-demo"
_demo_synced = False


async def ensure_demo_company() -> None:
    """Keep one persistent demo company with admin, reviewer and creator logins (password: DEMO_PASSWORD).

    Built once with the same seeded drafts a sandbox gets; passwords follow DEMO_PASSWORD on each restart.
    """
    global _demo_synced
    password = get_settings().demo_password
    if not password or _demo_synced:
        return
    from app.security import hash_password, verify_password

    async with SessionLocal() as session:
        org = await session.scalar(select(Organization).where(Organization.slug == DEMO_SLUG))
        if org is None:
            brand = load_brand(DEMO_BRAND)
            org, users = await create_org(session, brand, slug=DEMO_SLUG, is_sandbox=False,
                                          passwords={u["role"]: password for u in brand["users"]})
            await session.commit()
            await _seed_drafts(session, org, users)
            log.info("demo company %s created", DEMO_SLUG)
        else:
            for user in (await session.scalars(select(User).where(User.org_id == org.id))).all():
                if not verify_password(password, user.password_hash):
                    user.password_hash = hash_password(password)
        await session.commit()
    _demo_synced = True
