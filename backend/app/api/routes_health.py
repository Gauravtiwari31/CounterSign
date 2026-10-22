from fastapi import APIRouter, Depends
from sqlalchemy import text
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
    db_ok = (await session.scalar(text("SELECT 1"))) == 1
    vector_ok = bool(await session.scalar(text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")))
    return {
        "ok": db_ok and vector_ok,
        "db": db_ok, "pgvector": vector_ok,
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
