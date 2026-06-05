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
    # Embedding model for the note/tag-description vectors (spec §9.2 768-dim, M4+).
    gemini_embedding_model: str = Field(
        default="gemini-embedding-001", description="Gemini model id for embeddings"
    )
    worker_max_attempts: int = Field(
        default=3, description="Retry ceiling before an entry is marked failed"
    )

    # Auto-tagging knobs (spec §7.2, §15). Deliberately the only tuning knobs: the spec's
    # anti-fragmentation choices are a HIGH snap threshold (bias to under-merge live) and a
    # small 3-5 tag cap (bias to reuse over invention). Resist adding more (YAGNI).
    canonicalize_threshold: float = Field(
        default=0.90,
        description="Cosine >= this snaps a candidate tag to an existing one (spec §7.2)",
    )
    tags_per_entry_max: int = Field(
        default=5, description="Maximum tags assigned to one entry (spec §7.2 cap)"
    )
    tags_per_entry_min: int = Field(
        default=3, description="Target minimum tags per entry (spec §7.2)"
    )
    # Cap on existing tags pulled into the LLM prompt so it stays small at hundreds of
    # tags (spec §7.2: "at hundreds of tags they won't fit the prompt").
    nearest_tags_limit: int = Field(
        default=10, description="Max nearest existing tags shown to the tagger (spec §7.2)"
    )


@lru_cache
def get_settings() -> Settings:
    """Return the cached singleton Settings instance."""
    return Settings()
