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


# Input bounds (spec §7.3): titles/URLs are short; bodies (captured_text/note) get a
# larger but still bounded cap so a buggy/hostile client can't persist or FTS-index a
# multi-MB blob. Overflow yields a 422 instead of a silently stored blob.
_MAX_SHORT = 2_048  # title, url, source_url
_MAX_BODY = 262_144  # captured_text, note (~256 KB)


class CreateEntryRequest(BaseModel):
    """Body for POST /entries.

    Tagging, summarization, and indexing are async (spec §8.2), so callers send
    only the raw capture — never tags.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    type: EntryType = Field(description="Capture type: page, clip, conversation, or note")
    url: str | None = Field(
        default=None,
        max_length=_MAX_SHORT,
        description="Source URL; normalized for dedup (not used for notes)",
    )
    title: str | None = Field(
        default=None, max_length=_MAX_SHORT, description="Page <title> or OG title"
    )
    captured_text: str | None = Field(
        default=None,
        max_length=_MAX_BODY,
        description="Raw captured text; persisted only for clip/conversation/note",
    )
    note: str | None = Field(
        default=None,
        max_length=_MAX_BODY,
        description="Note override (spec §10): authored note text; skips LLM summarization",
    )
    source_url: str | None = Field(
        default=None,
        max_length=_MAX_SHORT,
        description="For clips: the page the selection came from",
    )

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


class RepairEntryRequest(BaseModel):
    """Body for PATCH /entries/{id} repair (spec §7.4).

    The user fills the note (and optionally tags) to recover a failed entry. On submit the
    entry re-enters processing using this note as the basis.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    note: str = Field(min_length=1, max_length=_MAX_BODY, description="User-authored note; the new processing basis")
    tags: list[str] | None = Field(
        default=None, description="Optional user-supplied tags; canonicalized + merged additively"
    )


class EntryResponse(BaseModel):
    """The full entry returned by PATCH repair (spec §7.4)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    url: str | None = None
    title: str | None = None
    note: str | None = None
    note_source: str
    type: str
    status: str
    saved_at: str
    updated_at: str
    error_message: str | None = None


class FailedEntry(BaseModel):
    """One failed entry in the 'needs attention' surface (spec §7.4)."""

    id: str
    url: str | None = None
    title: str | None = None
    note: str | None = None
    error_message: str | None = None
    updated_at: str


class FailedEntriesResponse(BaseModel):
    """The failed-entry surface for the §7.4 'needs attention' badge/dashboard."""

    total: int = Field(description="Total failed entries for the current user")
    entries: list[FailedEntry]
