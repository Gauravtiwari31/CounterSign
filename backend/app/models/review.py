import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk

FINDING_STATUSES = ("open", "accepted", "edited", "dismissed", "overridden", "resolved")


class ReviewJob(Base):
    __tablename__ = "review_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    draft_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("draft_versions.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    lane_status: Mapped[dict] = mapped_column(JSONB, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    ai_degraded: Mapped[bool] = mapped_column(default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timings: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = created_at_col()


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = uuid_pk()
    draft_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("draft_versions.id", ondelete="CASCADE"), index=True
    )
    lane: Mapped[str] = mapped_column(String(10))  # rules | claims | voice
    severity: Mapped[str] = mapped_column(String(10))  # blocking | warning | advisory | info
    source: Mapped[str] = mapped_column(String(10))  # rule | ai | pattern
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    span_text: Mapped[str] = mapped_column(Text)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    rule_code: Mapped[str | None] = mapped_column(String(20))
    criterion_code: Mapped[str | None] = mapped_column(String(20))
    fact_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    claim_type: Mapped[str | None] = mapped_column(String(30))
    claim_text: Mapped[str | None] = mapped_column(Text)
    claim_label: Mapped[str | None] = mapped_column(String(20))
    evidence: Mapped[list] = mapped_column(JSONB, default=list)
    message: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text, default="")
    regulatory_prompt: Mapped[str | None] = mapped_column(Text)
    suggestion: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="open")
    carried_from: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    model: Mapped[str | None] = mapped_column(String(80))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = created_at_col()


class FindingDecision(Base):
    __tablename__ = "finding_decisions"

    id: Mapped[uuid.UUID] = uuid_pk()
    finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("findings.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    actor_role: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(20))  # accept | edit | dismiss | override | reopen
    reason: Mapped[str | None] = mapped_column(Text)
    edited_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
