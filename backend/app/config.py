from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # project-root .env first, then backend/.env; real environment variables win over both
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+asyncpg://countersign:countersign@localhost:5432/countersign"
    # Render sets IS_PULL_REQUEST=true on PR preview instances, which copy the base service's env vars.
    # Previews must use PREVIEW_DATABASE_URL so a PR branch never migrates or writes the production DB.
    is_pull_request: bool = False
    preview_database_url: str = ""
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
    llm_timeout_s: float = 40.0  # one compact call does the work of several smaller ones
    llm_thinking_level: str = ""  # Gemini 3 thinkingConfig.thinkingLevel (minimal | low | ...); empty = model default
    # compact: 1 call per review (+1 only to verify fixes); full: separate extract/judge/voice/fix/re-check calls (~7)
    llm_mode: str = "compact"
    llm_concurrency: int = 4
    log_prompts: bool = False
    llm_data_use: str = (
        "Gemini API on the free tier: Google may use prompts and responses to improve its products. Personal data is "
        "masked before every call and only synthetic brand data is used in the demo. Set LLM_DATA_USE when moving "
        "to a paid project."
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
        if self.is_pull_request:
            if not self.preview_database_url:
                raise RuntimeError("PR preview without PREVIEW_DATABASE_URL: refusing to use the production database")
            url = self.preview_database_url
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
