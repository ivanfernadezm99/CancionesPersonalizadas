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
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""

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

    # Clip chaining settings
    CLIP_DURATION: int = 30
    CLIP_CROSSFADE_MS: int = 2500
    MAX_CLIPS: int = 6
    MAX_PARALLEL: int = 3
    CLIP_RETRY_ATTEMPTS: int = 2

    @field_validator("OPENCLAW_BASE_URL")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    def has_any_llm_key(self) -> bool:
        """Return True if at least one LLM API key is configured."""
        return bool(self.OPENAI_API_KEY or self.GEMINI_API_KEY or self.OPENROUTER_API_KEY)


settings = Settings()
