from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # project-root .env first, then backend/.env; real environment variables win over both
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+asyncpg://countersign:countersign@localhost:5432/countersign"
    jwt_secret: str = "dev-only-change-me"
    jwt_ttl_hours: int = 48
    cookie_secure: bool = False
    cookie_samesite: str = "lax"  # use "none" for cross-origin (Cloudflare → Render)

    # LLM providers. Model strings are pinned here and shown in Settings -> External services.
    llm_primary_provider: str = "gemini"
    llm_primary_model: str = "gemini-3.5-flash"
    gemini_api_key: str = ""
    llm_fallback_provider: str = "gemini"
    llm_fallback_model: str = "gemini-3.5-flash-lite"
    groq_api_key: str = ""
    llm_timeout_s: float = 20.0
    llm_concurrency: int = 4
    log_prompts: bool = False
    llm_data_use: str = (
        "Gemini API on a billing-enabled project (paid-tier terms: prompts are not used to improve Google products). "
        "Groq fallback. Only synthetic brand data is used in the demo."
    )

    embeddings: str = "auto"  # auto | fastembed | hash
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    pii_engine: str = "auto"  # auto | presidio | regex

    # CORS: comma-separated origins allowed to call the API (e.g. "https://countersign-5s3.pages.dev")
    cors_origins: str = ""

    hosting: str = "Single container (FastAPI + React SPA) with Neon Postgres"
    static_dir: str = "../frontend/dist"
    run_worker: bool = True
    sandbox_ttl_hours: int = 48
    sandbox_pool_size: int = 2
    reviews_per_hour: int = 30
    demo_sessions_per_hour_per_ip: int = 30

    @property
    def async_database_url(self) -> str:
        """Accept the plain URLs Neon and docker give out and turn them into an asyncpg URL."""
        url = self.database_url
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                url = "postgresql+asyncpg://" + url[len(prefix):]
        url = url.replace("sslmode=require", "ssl=require")
        if "channel_binding=" in url:
            base, _, query = url.partition("?")
            parts = [p for p in query.split("&") if not p.startswith("channel_binding=")]
            url = base + ("?" + "&".join(parts) if parts else "")
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
