"""Note-source fallback ladder (spec §7.3) — one cohesive resolver.

Resolves the note for an entry and records its provenance (``note_source``):

- ``note`` type: the user's text IS the note. No LLM. note_source = ``user``.
- ``clip`` / ``conversation``: use the persisted ``content``. A clip under
  ~400 chars IS the note verbatim (no LLM); otherwise summarize. note_source = ``body``.
- ``page``: the body is not persisted, so re-fetch the URL and extract, then walk the
  ladder: parsed body -> og:description / meta -> title alone. Summarize the body;
  take the og/meta teaser and the title verbatim. note_source = ``body|og|title``.

External services (page fetch, summarization) are injected as provider abstractions so
this stays unit-testable offline.
"""

from dataclasses import dataclass

from brain2.services.providers.page_fetcher import PageFetcher
from brain2.services.providers.summarizer import Summarizer

# A clip shorter than this is its own note — summarizing a highlight loses the value
# the user deliberately selected (spec §7.3).
_SHORT_CLIP_MAX_CHARS = 400


@dataclass(frozen=True)
class ResolvedNote:
    """The resolved note plus its provenance (spec §9.1 ``note`` / ``note_source``)."""

    note: str
    note_source: str


def resolve_note(
    entry: dict,
    *,
    fetcher: PageFetcher,
    summarizer: Summarizer,
) -> ResolvedNote:
    """Resolve the note + note_source for an entry (spec §7.3).

    ``entry`` is a row-like mapping carrying ``type``, ``url``, ``title``, ``content``.
    """
    entry_type = entry["type"]

    # A user-authored note is the note itself; never summarized, never re-fetched.
    if entry_type == "note":
        return ResolvedNote(note=entry.get("content") or "", note_source="user")

    # Persisted-body types (clip/conversation): use stored content, summarizing only
    # when it is long enough that a summary adds value over the raw text.
    if entry_type != "page":
        return _resolve_from_text(entry.get("content") or "", summarizer)

    # page: body is not persisted -> re-fetch and walk the ladder.
    return _resolve_page(entry, fetcher, summarizer)


def _resolve_from_text(text: str, summarizer: Summarizer) -> ResolvedNote:
    """Resolve a note from persisted body text (clip/conversation)."""
    if len(text) < _SHORT_CLIP_MAX_CHARS:
        # Short highlight: the selection is the note.
        return ResolvedNote(note=text, note_source="body")
    return ResolvedNote(note=summarizer.summarize(text), note_source="body")


def _resolve_page(entry: dict, fetcher: PageFetcher, summarizer: Summarizer) -> ResolvedNote:
    """Re-fetch a page and resolve via body -> og/meta -> title (spec §7.3 ladder)."""
    page = fetcher.fetch(entry["url"])

    body = (page.body_text or "").strip()
    if body:
        return ResolvedNote(note=summarizer.summarize(body), note_source="body")

    # og:description / meta description rung — publisher teaser copy, taken verbatim.
    teaser = _first_nonempty(page.og_description, page.meta_description)
    if teaser:
        return ResolvedNote(note=teaser, note_source="og")

    # Title rung — extracted title, else the entry's stored title.
    title = _first_nonempty(page.title, entry.get("title"))
    return ResolvedNote(note=title or "", note_source="title")


def _first_nonempty(*values: str | None) -> str | None:
    """First value that is non-empty after stripping, else None."""
    for value in values:
        if value and value.strip():
            return value.strip()
    return None
