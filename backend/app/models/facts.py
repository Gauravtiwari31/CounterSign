import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import EMBED_DIM, Base, created_at_col, uuid_pk


class Fact(Base):
    __tablename__ = "facts"
    __table_args__ = (
        Index("ix_facts_embedding_hnsw", "embedding", postgresql_using="hnsw",
              postgresql_ops={"embedding": "vector_cosine_ops"}),
        Index("ix_facts_tsv", "tsv", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    statement: Mapped[str] = mapped_column(Text)
    source_document: Mapped[str] = mapped_column(String(200), default="")
    source_locator: Mapped[str] = mapped_column(String(200), default="")
    owner: Mapped[str] = mapped_column(String(120), default="")
    scope_products: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    scope_channels: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    scope_regions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    embedding = mapped_column(Vector(EMBED_DIM), nullable=True)
    tsv = mapped_column(TSVECTOR, Computed("to_tsvector('english', statement)", persisted=True))
    introduced_in: Mapped[int] = mapped_column(Integer, default=1)
    retired_in: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at_col()
