"""Application settings (spec §12).

Reads the repo-root ``.env`` (one level above ``backend/``) via pydantic-settings.
Secrets (Gemini / Google OAuth) are optional placeholders here — milestones 1-2 make
no external calls — and are never hardcoded. Access settings through ``get_settings()``.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/brain2/config.py -> repo root is three parents up from this file.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DATA_DIR = _REPO_ROOT / "data" / "users"


class Settings(BaseSettings):
    """Backend configuration, populated from the repo-root .env and the environment."""

    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Per-user SQLite DB files live under this directory (gitignored).
    data_dir: Path = Field(default=_DEFAULT_DATA_DIR, description="Directory holding {user_id}.db files")

    # Dev auth stub: real auth (Google OAuth + API keys) arrives in M7.
    dev_user_id: str = Field(default="dev-user", description="Fixed user id used until auth lands")

    # External-service secrets. Optional placeholders; read from env when present.
    gemini_api_key: str | None = Field(default=None, description="Gemini API key (async enrichment, M3+)")
    google_client_id: str | None = Field(default=None, description="Google OAuth client id (M7)")
    google_client_secret: str | None = Field(default=None, description="Google OAuth client secret (M7)")

    # Async worker knobs (spec §7.4). Verified against the gemini-api-dev skill: the
    # current Flash model is gemini-3.5-flash; the embedding model (used in M4) is
    # gemini-embedding-001 at 768-dim.
    gemini_summary_model: str = Field(
        default="gemini-3.5-flash", description="Gemini model id for note summarization"
    )
    worker_max_attempts: int = Field(
        default=3, description="Retry ceiling before an entry is marked failed"
    )


@lru_cache
def get_settings() -> Settings:
    """Return the cached singleton Settings instance."""
    return Settings()
