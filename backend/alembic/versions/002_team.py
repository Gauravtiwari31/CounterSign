"""Team accounts: invite links and deactivated users.

Revision ID: 002
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

# 001 builds tables from the current models, so on a fresh database these already exist: IF NOT EXISTS keeps
# this migration correct for both fresh and existing databases.
UPGRADE = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS deactivated_at TIMESTAMPTZ",
    """CREATE TABLE IF NOT EXISTS invites (
        id UUID PRIMARY KEY,
        org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        email VARCHAR(200) NOT NULL,
        name VARCHAR(120) NOT NULL,
        role VARCHAR(20) NOT NULL,
        token_hash VARCHAR(64) NOT NULL UNIQUE,
        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
        created_by UUID REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        accepted_at TIMESTAMPTZ
    )""",
    "CREATE INDEX IF NOT EXISTS ix_invites_org_id ON invites (org_id)",
]


def upgrade() -> None:
    for stmt in UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS invites")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS deactivated_at")
