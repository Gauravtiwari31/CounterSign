"""Append-only, hash-chained audit log.

hash = sha256(prev_hash || canonical_json(event)). The DB trigger blocks UPDATE/DELETE;
the chain makes any out-of-band edit detectable by `verify_chain`.
"""
import hashlib
import json
import uuid
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent, utcnow

GENESIS = "0" * 64


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _event_body(org_id, actor_id, entity_type, entity_id, action, payload, created_at: datetime) -> dict:
    return {
        "org_id": str(org_id),
        "actor_id": str(actor_id) if actor_id else None,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "action": action,
        "payload": payload,
        "created_at": created_at.isoformat(),
    }


def compute_hash(prev_hash: str, body: dict) -> str:
    return hashlib.sha256((prev_hash + canonical_json(body)).encode()).hexdigest()


async def append_event(
    session: AsyncSession,
    org_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    entity_type: str,
    entity_id,
    action: str,
    payload: dict | None = None,
) -> AuditEvent:
    payload = json.loads(canonical_json(payload or {}))
    # serialise appends per org so the chain cannot fork
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"audit:{org_id}"})
    prev = await session.scalar(
        select(AuditEvent.hash).where(AuditEvent.org_id == org_id).order_by(AuditEvent.id.desc()).limit(1)
    )
    prev_hash = prev or GENESIS
    created_at = utcnow()
    body = _event_body(org_id, actor_id, entity_type, entity_id, action, payload, created_at)
    event = AuditEvent(
        org_id=org_id, actor_id=actor_id, entity_type=entity_type, entity_id=str(entity_id), action=action,
        payload=payload, created_at=created_at, prev_hash=prev_hash, hash=compute_hash(prev_hash, body),
    )
    session.add(event)
    await session.flush()
    return event


async def verify_chain(session: AsyncSession, org_id: uuid.UUID) -> dict:
    events = (
        await session.scalars(select(AuditEvent).where(AuditEvent.org_id == org_id).order_by(AuditEvent.id))
    ).all()
    prev_hash = GENESIS
    for ev in events:
        body = _event_body(ev.org_id, ev.actor_id, ev.entity_type, ev.entity_id, ev.action, ev.payload, ev.created_at)
        if ev.prev_hash != prev_hash or compute_hash(prev_hash, body) != ev.hash:
            return {"ok": False, "events": len(events), "broken_at": ev.id}
        prev_hash = ev.hash
    return {"ok": True, "events": len(events), "head": prev_hash}
