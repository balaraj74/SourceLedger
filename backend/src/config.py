"""Application configuration loaded from environment variables.

Follows twelve-factor config: all secrets and environment-specific
settings come from env vars, never hardcoded. Copy .env.example to
.env and fill in real values before running.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for the SourceLedger backend.

    Every setting can be overridden by an environment variable of the
    same name (case-insensitive). See .env.example for documentation
    of each setting.
    """

    # ── LLM API & Gateway Proxy ───────────────────────────────────────
    google_api_key: str = ""
    google_api_key1: str = ""
    google_api_key2: str = ""
    google_api_key3: str = ""
    google_api_key4: str = ""
    google_api_key5: str = ""
    google_api_key6: str = ""
    google_api_key7: str = ""
    google_api_key8: str = ""
    openai_api_key: str = ""
    api_url: str = "https://free-api-erel.onrender.com/api/generate"
    api_key: str = "sk_proxy_qu7f0nNyFooVFjM3iNb_lmwZr_NP-BuL"

    # Gemini Round-Robin Gateway Proxy Settings
    gemini_proxy_url: str = "https://free-api-erel.onrender.com/api/generate"
    gemini_proxy_token: str = "sk_proxy_qu7f0nNyFooVFjM3iNb_lmwZr_NP-BuL"
    proxy_auth_token: str = "sk_proxy_qu7f0nNyFooVFjM3iNb_lmwZr_NP-BuL"
    proxy_url: str = "https://free-api-erel.onrender.com/api/generate"

    def get_google_api_keys(self) -> list[str]:
        """Collect all configured Google Gemini API keys."""
        keys = []
        for i in range(1, 9):
            key = getattr(self, f"google_api_key{i}", "").strip()
            if key and key not in keys:
                keys.append(key)
        if self.google_api_key.strip() and self.google_api_key.strip() not in keys:
            keys.append(self.google_api_key.strip())
        return keys

    # ── Database ─────────────────────────────────────────────────────
    database_url: str = (
        "postgresql+asyncpg://sourceledger:sourceledger@localhost:5432/sourceledger"
    )

    # ── Vector DB (stretch — Phase 5) ────────────────────────────────
    qdrant_url: str = "http://localhost:6333"

    # ── App ──────────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"

    # Fields with confidence below this threshold route to the review
    # queue instead of being auto-committed.
    confidence_threshold: int = 70

    # ── Storage ──────────────────────────────────────────────────────
    source_storage_path: str = "./storage/sources"

    # ── Supabase Database ──────────────────────────────────────────────
    supabase_org: str = "sourceLedge"
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_role_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
