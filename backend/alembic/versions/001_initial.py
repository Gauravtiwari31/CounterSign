"""Initial schema: all tables, pgvector, append-only audit trigger.

Revision ID: 001
"""
from alembic import op

from app.models import Base

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

AUDIT_GUARD = ["""
CREATE OR REPLACE FUNCTION audit_events_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' AND EXISTS (
        SELECT 1 FROM organizations o
        WHERE o.id = OLD.org_id AND o.is_sandbox AND o.expires_at IS NOT NULL AND o.expires_at < now()
    ) THEN
        -- the only permitted delete: retention purge of an expired demo sandbox
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'audit_events is append-only (% blocked)', TG_OP;
END;
$$ LANGUAGE plpgsql""", """
CREATE TRIGGER audit_events_append_only
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION audit_events_guard()""", """
CREATE OR REPLACE FUNCTION audit_events_no_truncate() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only (TRUNCATE blocked)';
END;
$$ LANGUAGE plpgsql""", """
CREATE TRIGGER audit_events_no_truncate
BEFORE TRUNCATE ON audit_events
FOR EACH STATEMENT EXECUTE FUNCTION audit_events_no_truncate()"""]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=op.get_bind())
    for stmt in AUDIT_GUARD:  # asyncpg runs one statement per call
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_truncate ON audit_events")
    op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events")
    Base.metadata.drop_all(bind=op.get_bind())
