"""Create a persistent workspace with password logins: python -m app.seed.cli [brand] [--password PW]."""
import argparse
import asyncio
import secrets

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Organization
from app.seed.loader import brand_keys, create_org, load_brand


async def main(brand_key: str, password: str) -> None:
    brand = load_brand(brand_key)
    slug = brand_key.replace("_", "-")
    async with SessionLocal() as session:
        if await session.scalar(select(Organization.id).where(Organization.slug == slug)):
            print(f"Workspace '{slug}' already exists")
            return
        await create_org(session, brand, slug=slug, is_sandbox=False,
                         passwords={u["role"]: password for u in brand["users"]})
        await session.commit()
    print(f"Created workspace '{slug}'. Log in with any of:")
    for u in brand["users"]:
        print(f"  {u['role']:9} {u['email']}")
    print(f"Password: {password}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("brand", nargs="?", default="verdant_skin", choices=brand_keys())
    ap.add_argument("--password", default=None)
    args = ap.parse_args()
    asyncio.run(main(args.brand, args.password or secrets.token_urlsafe(12)))
