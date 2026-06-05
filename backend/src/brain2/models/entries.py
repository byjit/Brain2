"""Pydantic request/response models for the entries API (spec §9.1, §10)."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EntryType(str, Enum):
    """Capture types (spec §7.3)."""

    PAGE = "page"
    CLIP = "clip"
    CONVERSATION = "conversation"
    NOTE = "note"


class SaveStatus(str, Enum):
    """Result of an upsert: a fresh insert vs. an update of an existing URL."""

    SAVED = "saved"
    UPDATED = "updated"


class CreateEntryRequest(BaseModel):
    """Body for POST /entries.

    Tagging, summarization, and indexing are async (spec §8.2), so callers send
    only the raw capture — never tags.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    type: EntryType = Field(description="Capture type: page, clip, conversation, or note")
    url: str | None = Field(default=None, description="Source URL; normalized for dedup (not used for notes)")
    title: str | None = Field(default=None, description="Page <title> or OG title")
    captured_text: str | None = Field(
        default=None,
        description="Raw captured text; persisted only for clip/conversation/note",
    )
    source_url: str | None = Field(default=None, description="For clips: the page the selection came from")

    @model_validator(mode="after")
    def _validate_by_type(self) -> "CreateEntryRequest":
        """URL-backed types need a URL; notes need their text (their only copy)."""
        if self.type == EntryType.NOTE:
            if not self.captured_text:
                raise ValueError("captured_text is required for type 'note'")
        else:
            if not self.url:
                raise ValueError(f"url is required for type '{self.type.value}'")
        return self


class SaveEntryResponse(BaseModel):
    """Immediate response from POST /entries (spec §7.1 step 4)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Entry id (nanoid)")
    status: SaveStatus = Field(description="'saved' for a new entry, 'updated' for an existing URL")
