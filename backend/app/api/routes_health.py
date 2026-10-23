import re
import time

from fastapi import APIRouter, Depends
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import embeddings, pii
from app.config import get_settings
from app.db import get_session
from app.deps import Principal, current_principal
from app.llm import adapter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health():
    return {"ok": True}


@router.get("/health/deep")
async def health_deep(session: AsyncSession = Depends(get_session)):
    t0 = time.perf_counter()
    db_ok = (await session.scalar(text("SELECT 1"))) == 1
    t1 = time.perf_counter()
    vector_ok = bool(await session.scalar(text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")))
    t2 = time.perf_counter()
    # region only (never the host or credentials): the API and its database must share a region
    host = make_url(get_settings().async_database_url).host or ""
    region = re.search(r"\.([a-z]{2}-[a-z]+-\d)\.aws\.neon\.tech$", host)
    return {
        "ok": db_ok and vector_ok,
        "db": db_ok, "pgvector": vector_ok,
        "db_region": region.group(1) if region else "not neon",
        "db_first_query_ms": round((t1 - t0) * 1000), "db_query_ms": round((t2 - t1) * 1000),
        "embeddings": embeddings.engine_name(),
        "llm_configured": adapter.configured(),
        "llm_last_ok_provider": adapter.stats.last_ok_provider,
        "llm_stats": {"calls": adapter.stats.calls, "cache_hits": adapter.stats.cache_hits,
                      "failures": adapter.stats.failures, "repairs": adapter.stats.repairs},
    }


@router.get("/settings/services")
async def services(p: Principal = Depends(current_principal)):
    s = get_settings()
    providers = adapter.providers()
    return {
        "llm": [{"role": "primary" if i == 0 else "fallback", "provider": prov.name, "model": prov.model}
                for i, prov in enumerate(providers)],
        "llm_configured": bool(providers),
        "llm_note": None if providers else
        "No LLM key is configured, so claims are flagged by the pattern fallback and need human review.",
        "llm_data_use": s.llm_data_use,
        "embeddings": embeddings.engine_name(),
        "pii_masking": pii.engine_name(),
        "hosting": s.hosting,
        "database": "PostgreSQL 16 + pgvector (Neon in production)",
        "data_sent_to_llm": "Masked draft text, rulebook voice criteria and fact statements. Personal data is "
                            "replaced with placeholders before any call.",
    }
