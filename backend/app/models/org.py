import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk

ROLES = ("admin", "reviewer", "creator")


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    brand_key: Mapped[str | None] = mapped_column(String(60))
    region: Mapped[str] = mapped_column(String(10), default="IN")
    is_sandbox: Mapped[bool] = mapped_column(Boolean, default=False)
    rulebook_version: Mapped[int] = mapped_column(Integer, default=1)
    facts_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = created_at_col()
    # sandbox pool: a sandbox is pre-built, then claimed by one visitor
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("org_id", "email"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_at_col()
    # removing a person deactivates them: their drafts, decisions and audit events keep their name
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invite(Base):
    """A one-time link that lets someone join an organization, or set a new password (user_id set)."""

    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at_col()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
