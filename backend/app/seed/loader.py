"""Build an organisation from a brand YAML: users, rulebook, voice rubric, palette, facts (with embeddings)."""
import uuid
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_event
from app.embeddings import embed
from app.models import Fact, Organization, PaletteColor, Rule, User, VoiceCriterion

BRANDS_DIR = Path(__file__).parent / "brands"


@lru_cache
def load_brand(key: str) -> dict:
    return yaml.safe_load((BRANDS_DIR / f"{key}.yaml").read_text(encoding="utf-8"))


def brand_keys() -> list[str]:
    return sorted(p.stem for p in BRANDS_DIR.glob("*.yaml"))


def _date(v) -> date | None:
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


async def create_org(session: AsyncSession, brand: dict, *, slug: str, is_sandbox: bool,
                     passwords: dict[str, str] | None = None) -> tuple[Organization, dict[str, User]]:
    from app.security import hash_password

    org = Organization(name=brand["name"], slug=slug, brand_key=f"{brand['key']}@{brand['seed_version']}",
                       region=brand.get("region", "IN"), is_sandbox=is_sandbox)
    session.add(org)
    await session.flush()

    users: dict[str, User] = {}
    for u in brand["users"]:
        pw = (passwords or {}).get(u["role"])
        user = User(org_id=org.id, email=u["email"], name=u["name"], role=u["role"],
                    password_hash=hash_password(pw) if pw else None)
        session.add(user)
        users[u["role"]] = user
    await session.flush()
    admin = users.get("admin")

    for r in brand["rules"]:
        session.add(Rule(org_id=org.id, code=r["code"], type=r["type"], params=r.get("params", {}),
                         severity=r.get("severity", "warning"), channels=r.get("channels"), title=r.get("title", r["code"]),
                         description=r.get("description", ""), introduced_in=1, created_by=admin.id if admin else None))
    for v in brand.get("voice", []):
        session.add(VoiceCriterion(org_id=org.id, code=v["code"], title=v["title"], description=v.get("description", ""),
                                   good_examples=v.get("good", []), bad_examples=v.get("bad", []), introduced_in=1))
    for c in brand.get("palette", []):
        session.add(PaletteColor(org_id=org.id, name=c["name"], hex=c["hex"], role=c["role"]))

    facts_yaml = brand.get("facts", [])
    vectors = embed([f["statement"] for f in facts_yaml])
    ids = {f["code"]: uuid.uuid4() for f in facts_yaml}
    for f, vec in zip(facts_yaml, vectors, strict=False):
        session.add(Fact(
            id=ids[f["code"]], org_id=org.id, code=f["code"], statement=f["statement"],
            source_document=f.get("source_document", ""), source_locator=str(f.get("source_locator", "")),
            owner=f.get("owner", ""), scope_products=f.get("products", []), scope_channels=f.get("channels", []),
            scope_regions=f.get("regions", []), valid_from=_date(f.get("valid_from")), valid_to=_date(f.get("valid_to")),
            superseded_by=ids.get(f.get("superseded_by")), embedding=vec, introduced_in=1,
            created_by=admin.id if admin else None,
        ))
    await session.flush()
    await append_event(session, org.id, None, "organization", org.id, "organization.created",
                       {"brand": org.brand_key, "sandbox": is_sandbox, "rules": len(brand["rules"]),
                        "facts": len(facts_yaml)})
    return org, users
