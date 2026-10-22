import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.audit import append_event, verify_chain
from app.db import SessionLocal
from app.models import Organization

pytestmark = pytest.mark.db


async def _org(session) -> Organization:
    org = Organization(name="Audit Test", slug=f"audit-{id(session)}", is_sandbox=False)
    session.add(org)
    await session.flush()
    return org


async def test_chain_verifies_and_db_blocks_update_and_delete():
    async with SessionLocal() as s:
        org = await _org(s)
        for i in range(3):
            await append_event(s, org.id, None, "test", i, "test.event", {"i": i})
        await s.commit()
        assert (await verify_chain(s, org.id))["ok"]
        org_id = org.id

    for stmt in ("UPDATE audit_events SET action = 'x' WHERE org_id = :o",
                 "DELETE FROM audit_events WHERE org_id = :o"):
        async with SessionLocal() as s:
            with pytest.raises(DBAPIError, match="append-only"):
                await s.execute(text(stmt), {"o": org_id})


async def test_tampering_is_detected():
    async with SessionLocal() as s:
        org = await _org(s)
        for i in range(3):
            await append_event(s, org.id, None, "test", i, "test.event", {"i": i})
        await s.commit()
        # simulate an attacker with superuser rights bypassing the trigger
        await s.execute(text("ALTER TABLE audit_events DISABLE TRIGGER audit_events_append_only"))
        await s.execute(text("UPDATE audit_events SET payload = '{\"i\": 99}' WHERE org_id = :o AND entity_id = '1'"),
                        {"o": org.id})
        await s.execute(text("ALTER TABLE audit_events ENABLE TRIGGER audit_events_append_only"))
        await s.commit()
        result = await verify_chain(s, org.id)
        assert not result["ok"]
