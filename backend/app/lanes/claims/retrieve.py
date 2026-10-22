"""Step 2 - Retrieve (code). Full-text + vector, fused with Reciprocal Rank Fusion, scope-filtered.

Expired and superseded facts are deliberately included: expiry is decided in code at step 5,
which is how an outdated claim becomes visible as EXPIRED instead of UNSUPPORTED.
"""
import re
import uuid

from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings import embed
from app.lanes.types import Claim, FactRow
from app.models import Fact

RRF_K = 60
TOP_K = 10
KEEP = 8

FTS_SQL = text("""
SELECT f.id FROM facts f,
     to_tsquery('english', replace(plainto_tsquery('english', :q)::text, '&', '|')) q
WHERE f.org_id = :org AND f.introduced_in <= :v AND (f.retired_in IS NULL OR f.retired_in > :v)
  AND f.tsv @@ q
ORDER BY ts_rank(f.tsv, q) DESC
LIMIT :k
""")


def active_facts_clause(org_id: uuid.UUID, version: int):
    return and_(Fact.org_id == org_id, Fact.introduced_in <= version,
                or_(Fact.retired_in.is_(None), Fact.retired_in > version))


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _same_product(a: str, b: str) -> bool:
    """'AloeCalm Soothing Gel' and 'AloeCalm' name the same product; so do 'ClearDew' and 'ClearDew Serum'."""
    ka, kb = _key(a), _key(b)
    return bool(ka and kb) and (ka in kb or kb in ka)


def in_scope(fact: FactRow, product: str | None, channel: str, region: str) -> bool:
    if product and fact.scope_products and not any(_same_product(product, p) for p in fact.scope_products):
        return False
    if fact.scope_channels and channel not in fact.scope_channels:
        return False
    if fact.scope_regions and region not in fact.scope_regions:
        return False
    return True


def to_row(f: Fact, code_by_id: dict) -> FactRow:
    return FactRow(
        id=f.id, code=f.code, statement=f.statement, source_document=f.source_document,
        source_locator=f.source_locator, owner=f.owner, valid_from=f.valid_from, valid_to=f.valid_to,
        superseded_by=f.superseded_by, scope_products=f.scope_products or [], scope_channels=f.scope_channels or [],
        scope_regions=f.scope_regions or [], superseded_by_code=code_by_id.get(f.superseded_by),
    )


async def load_facts(session: AsyncSession, org_id: uuid.UUID, facts_version: int) -> dict[uuid.UUID, FactRow]:
    facts = (await session.scalars(select(Fact).where(active_facts_clause(org_id, facts_version)))).all()
    all_codes = dict((await session.execute(select(Fact.id, Fact.code).where(Fact.org_id == org_id))).all())
    return {f.id: to_row(f, all_codes) for f in facts}


async def retrieve(session: AsyncSession, org_id: uuid.UUID, facts_version: int, claims: list[Claim],
                   channel: str, region: str, facts: dict[uuid.UUID, FactRow]) -> None:
    if not claims:
        return
    vectors = embed([c.atomic for c in claims])
    for claim, vec in zip(claims, vectors, strict=False):
        fts_ids = (await session.execute(FTS_SQL, {"q": claim.atomic, "org": org_id, "v": facts_version, "k": TOP_K})).scalars().all()
        vec_ids = (await session.scalars(
            select(Fact.id).where(active_facts_clause(org_id, facts_version), Fact.embedding.is_not(None))
            .order_by(Fact.embedding.cosine_distance(vec)).limit(TOP_K)
        )).all()
        scores: dict[uuid.UUID, float] = {}
        for ranked in (fts_ids, vec_ids):
            for rank, fid in enumerate(ranked, start=1):
                scores[fid] = scores.get(fid, 0.0) + 1.0 / (RRF_K + rank)
        ordered = sorted(scores, key=scores.get, reverse=True)
        claim.candidates = [
            facts[fid] for fid in ordered if fid in facts and in_scope(facts[fid], claim.product, channel, region)
        ][:KEEP]
