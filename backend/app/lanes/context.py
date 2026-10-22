import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lanes.claims.retrieve import load_facts
from app.lanes.rules.engine import RuleSpec
from app.lanes.types import FactRow
from app.models import Organization, Rule, VoiceCriterion


@dataclass
class ReviewContext:
    org_id: uuid.UUID
    region: str
    brand_name: str
    channel: str
    purpose: str
    rulebook_version: int
    facts_version: int
    rules: list[RuleSpec]
    criteria: list[VoiceCriterion]
    facts: dict[uuid.UUID, FactRow]
    today: date = field(default_factory=date.today)

    @property
    def cache_extra(self) -> str:
        return f"rb{self.rulebook_version}|fv{self.facts_version}"

    def allow_terms(self) -> set[str]:
        terms = {self.brand_name}
        for r in self.rules:
            p = r.params
            terms.update(filter(None, [p.get("preferred"), *p.get("forbidden", []), *p.get("required", [])]))
        for f in self.facts.values():
            terms.update(f.scope_products)
        return {t for t in terms if t}

    def product_names(self) -> list[str]:
        names = {p for f in self.facts.values() for p in f.scope_products}
        names.update(r.params["preferred"] for r in self.rules if r.type == "terminology")
        return sorted(names, key=len, reverse=True)


def active_clause(model, org_id: uuid.UUID, version: int):
    return and_(model.org_id == org_id, model.introduced_in <= version,
                or_(model.retired_in.is_(None), model.retired_in > version))


def to_spec(r: Rule) -> RuleSpec:
    return RuleSpec(code=r.code, type=r.type, params=r.params, severity=r.severity, channels=r.channels,
                    title=r.title, description=r.description, id=str(r.id))


async def load_rule_specs(session: AsyncSession, org_id: uuid.UUID, version: int) -> list[RuleSpec]:
    rules = (await session.scalars(select(Rule).where(active_clause(Rule, org_id, version)).order_by(Rule.code))).all()
    return [to_spec(r) for r in rules]


async def build_context(session: AsyncSession, org: Organization, channel: str, purpose: str,
                        rulebook_version: int, facts_version: int) -> ReviewContext:
    criteria = (await session.scalars(
        select(VoiceCriterion).where(active_clause(VoiceCriterion, org.id, rulebook_version)).order_by(VoiceCriterion.code)
    )).all()
    return ReviewContext(
        org_id=org.id, region=org.region, brand_name=org.name, channel=channel, purpose=purpose,
        rulebook_version=rulebook_version, facts_version=facts_version,
        rules=await load_rule_specs(session, org.id, rulebook_version), criteria=list(criteria),
        facts=await load_facts(session, org.id, facts_version),
    )
