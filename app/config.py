"""Application configuration via pydantic-settings."""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Allow extra env vars without crashing
        extra="ignore",
    )

    # LLM API Keys (at least one required)
    ZEN_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""

    # Zen (OpenCode) model selection — cascade primary/secondary
    ZEN_PRIMARY_MODEL: str = "big-pickle"
    ZEN_SECONDARY_MODEL: str = "nemotron-3-ultra-free"

    # OpenClaw gateway
    OPENCLAW_TOKEN: str = ""
    OPENCLAW_BASE_URL: str = "http://localhost:18789"

    # Storage
    DB_PATH: str = "jobs.db"
    OUTPUT_DIR: str = "./output"

    # Job TTL in hours (default 24)
    JOB_TTL_HOURS: int = 24

    # Cleanup interval in seconds (default 3600 = 1h)
    CLEANUP_INTERVAL_SECONDS: int = 3600

    # Max concurrent jobs
    MAX_CONCURRENT_JOBS: int = 5

    # Project settings
    PREVIEW_TARGET_SECONDS: int = 30
    FINAL_TARGET_SECONDS: int = 150

    # Music provider selection
    MUSIC_PROVIDER: str = "openclaw"

    # Suno AI settings
    SUNO_API_KEY: str = ""
    SUNO_BASE_URL: str = ""
    SUNO_DEFAULT_MODEL: str = "V4_5"

    # Public URL for serving reference audio
    PUBLIC_BASE_URL: str = ""

    # Frontend base URL for payment success/failure redirects (hash-routed Angular app)
    FRONTEND_BASE_URL: str = ""

    # Clip chaining settings
    CLIP_DURATION: int = 30
    CLIP_CROSSFADE_MS: int = 2500
    MAX_CLIPS: int = 6
    MAX_PARALLEL: int = 3
    CLIP_RETRY_ATTEMPTS: int = 2

    # JWT Authentication
    JWT_JWKS_URL: str = ""  # deprecated — kept for backward compat, unused with HS256
    # issuer/audience validation disabled by default: POSBackend emits different
    # iss/aud per environment, which caused false 401s. The HS256 shared secret
    # is the real security boundary. Empty = skip iss/aud checks in the middleware.
    JWT_ISSUER: str = ""
    JWT_AUDIENCE: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_SHARED_SECRET: str = ""
    JWT_AUTH_ENFORCED: bool = True
    # Roles permitidos por DESCRIPCIÓN (POSBackend emite el nombre del rol en el
    # claim `role`, no el ID numérico). Vacío = permitir todo usuario autenticado.
    # Roles base de POSBackend: Administrador, Cajero, Supervisor, Vendedor, Almacén.
    JWT_ALLOWED_ROLES: frozenset[str] = frozenset()

    # Payment settings
    SONG_PRICE: float = 5.00
    PAYMENT_GATEWAY_URL: str = ""
    PAYMENT_WEBHOOK_SECRET: str = ""

    # Superadmin: comma-separated user IDs (POSBackend numeric User.Id) or
    # emails that can see ALL projects, not only their own.
    SUPERADMIN_USER_IDS: str = ""

    # Cloudflare Turnstile (anti-bot)
    TURNSTILE_SECRET_KEY: str = ""
    TURNSTILE_SITE_KEY: str = ""

    @field_validator("OPENCLAW_BASE_URL")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    def has_any_llm_key(self) -> bool:
        """Return True if at least one LLM API key is configured."""
        return bool(
            self.ZEN_API_KEY
            or self.OPENAI_API_KEY
            or self.GEMINI_API_KEY
            or self.OPENROUTER_API_KEY
        )


settings = Settings()


def is_superadmin(user_id: str = "", email: str = "") -> bool:
    """True when the user is listed in SUPERADMIN_USER_IDS (ids or emails)."""
    raw = settings.SUPERADMIN_USER_IDS or ""
    entries = {e.strip().lower() for e in raw.split(",") if e.strip()}
    if not entries:
        return False
    user_id = str(user_id or "").strip().lower()
    email = str(email or "").strip().lower()
    return user_id in entries or email in entries
