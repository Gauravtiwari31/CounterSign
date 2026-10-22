import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk

RULE_TYPES = (
    "terminology", "banned_phrase", "required_phrase", "punctuation_limit", "length_limit",
    "readability", "all_caps", "hashtag", "regex", "currency_format",
)


class Rule(Base):
    """Copy-on-write: editing retires the old row (retired_in) and inserts a new one."""

    __tablename__ = "rules"

    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    type: Mapped[str] = mapped_column(String(30))
    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    channels: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    introduced_in: Mapped[int] = mapped_column(Integer, default=1)
    retired_in: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at_col()


class VoiceCriterion(Base):
    __tablename__ = "voice_criteria"

    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    good_examples: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    bad_examples: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    introduced_in: Mapped[int] = mapped_column(Integer, default=1)
    retired_in: Mapped[int | None] = mapped_column(Integer)


class PaletteColor(Base):
    __tablename__ = "palette"

    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    hex: Mapped[str] = mapped_column(String(7))
    role: Mapped[str] = mapped_column(String(20))  # text | background | accent
