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

import re
from dataclasses import dataclass

from brain2.services.providers.page_fetcher import PageContent, PageFetcher
from brain2.services.providers.summarizer import SUMMARY_INPUT_MAX_CHARS, Summarizer

# A clip shorter than this is its own note — summarizing a highlight loses the value
# the user deliberately selected (spec §7.3).
_SHORT_CLIP_MAX_CHARS = 400

# Code-dominance heuristic (clip only). A short clip that is mostly CODE embeds poorly for
# paraphrase search — a query like "that debounce trick" won't match a bare snippet — so a
# code-dominant clip is captioned (summarize path) instead of taken verbatim. The verbatim
# code stays safe in ``content`` (persisted + FTS-indexed).
#
# CONSTRAINT — bias to verbatim/prose; only flip when CLEARLY code. A false positive turns a
# user's deliberate short prose into an LLM paraphrase, which is the worse failure (it loses
# the exact words the user chose). So the thresholds below are deliberately conservative:
# an occasional inline `identifier()` in prose must NOT trigger it.

# Lines that end in a statement/block delimiter or contain a code operator/idiom are "code-ish".
_CODE_LINE = re.compile(r"(;\s*$)|([{}]\s*$)|(=>)|(\(\)\s*;?\s*$)|(^\s+\S+\s*=\s*\S)")
# Fraction of non-blank lines that must look like code (with 2+ such lines) to call it code.
_CODE_LINE_RATIO = 0.5
_MIN_CODE_LINES = 2


def is_code_dominant(text: str) -> bool:
    """Return True when a short clip is dominated by code rather than prose.

    Conservative by design (see the module constant note): a Markdown code fence is treated
    as unambiguous code; otherwise a majority of the clip's non-blank lines must look like
    code before it flips. Empty/whitespace text is not code.
    """
    stripped = text.strip()
    if not stripped:
        return False

    # The element picker emits a Markdown fence for code blocks — treat that as definitive.
    if "```" in text:
        return True

    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < _MIN_CODE_LINES:
        # A single line is too little signal to reliably distinguish code from prose.
        return False

    code_lines = sum(1 for line in lines if _CODE_LINE.search(line))
    return code_lines >= _MIN_CODE_LINES and code_lines / len(lines) >= _CODE_LINE_RATIO


@dataclass(frozen=True)
class ResolvedNote:
    """The resolved note plus its provenance (spec §9.1 ``note`` / ``note_source``)."""

    note: str
    note_source: str


@dataclass(frozen=True)
class NoteBasis:
    """The note BASIS plus whether it still needs summarizing (spec §7.1 steps 2-3, 6).

    This decouples *finding the source text* (cheap, no LLM) from *producing the note*,
    so M5 can fold the summary into the single combined tagging call instead of making a
    separate summarizer call (spec §7.2 "exactly one LLM call per entry").

    - ``text`` is always the basis to embed for nearest-tag lookup (spec §7.1 step 3).
    - When ``needs_summary`` is True the note is produced downstream (by the tagger).
    - When False, ``note`` is the verbatim note already (user text / short clip / og / title).
    """

    text: str
    note_source: str
    needs_summary: bool
    note: str  # the verbatim note when needs_summary is False; "" otherwise
    # The fetched page (page entries only) so the caller can derive structured priors from
    # its OG/meta keywords without re-fetching (spec §7.2 mechanism 1). Empty otherwise.
    page: PageContent = PageContent()


def resolve_basis(entry: dict, *, fetcher: PageFetcher) -> NoteBasis:
    """Resolve the note basis WITHOUT summarizing (spec §7.1 steps 2-3).

    Mirrors :func:`resolve_note`'s source ladder but defers summarization: it returns the
    text to embed/summarize and a ``needs_summary`` flag, so the caller makes exactly one
    LLM call. The verbatim short-circuits (note / short clip / og / title) are preserved.
    """
    entry_type = entry["type"]

    if entry_type == "note":
        text = entry.get("content") or ""
        return NoteBasis(text=text, note_source="user", needs_summary=False, note=text)

    if entry_type != "page":
        text = entry.get("content") or ""
        # Short highlight: the selection IS the note (no LLM) — UNLESS it's a code-dominant
        # clip, which embeds poorly verbatim, so we caption it via the summarize path instead
        # (folded into the combined tagging call; no extra LLM call). Scope is `clip` only.
        if len(text) < _SHORT_CLIP_MAX_CHARS and not (
            entry_type == "clip" and is_code_dominant(text)
        ):
            return NoteBasis(text=text, note_source="body", needs_summary=False, note=text)
        return NoteBasis(text=text, note_source="body", needs_summary=True, note="")

    # page: check if client-scraped content was temporarily persisted first.
    body = (entry.get("content") or "").strip()
    if body:
        return NoteBasis(
            text=body,
            note_source="body",
            needs_summary=True,
            note="",
            page=PageContent(body_text=body, title=entry.get("title")),
        )

    # fallback: re-fetch and walk the ladder. The fetched page is carried
    # on the result so the caller can derive OG/meta-keyword priors without re-fetching.
    page = fetcher.fetch(entry["url"])
    body = (page.body_text or "").strip()
    if body:
        return NoteBasis(text=body, note_source="body", needs_summary=True, note="", page=page)

    teaser = _first_nonempty(page.og_description, page.meta_description)
    if teaser:
        return NoteBasis(
            text=teaser, note_source="og", needs_summary=False, note=teaser, page=page
        )

    title = _first_nonempty(page.title, entry.get("title")) or ""
    return NoteBasis(text=title, note_source="title", needs_summary=False, note=title, page=page)


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
        return _resolve_from_text(entry.get("content") or "", summarizer, entry_type=entry_type)

    # page: body is not persisted -> re-fetch and walk the ladder.
    return _resolve_page(entry, fetcher, summarizer)


def _resolve_from_text(text: str, summarizer: Summarizer, *, entry_type: str) -> ResolvedNote:
    """Resolve a note from persisted body text (clip/conversation).

    Mirrors :func:`resolve_basis`: a short highlight is the note verbatim, EXCEPT a
    code-dominant ``clip``, which is captioned (summarized) so its vector is paraphrase-
    searchable — the verbatim code stays safe in ``content`` (spec §7.3).
    """
    if len(text) < _SHORT_CLIP_MAX_CHARS and not (
        entry_type == "clip" and is_code_dominant(text)
    ):
        # Short highlight: the selection is the note.
        return ResolvedNote(note=text, note_source="body")
    # Summarize a bounded prefix: the note is a routing card, not a full recap (spec §7.3),
    # and the full text stays FTS-searchable, so a prefix is enough and caps LLM cost.
    return ResolvedNote(
        note=summarizer.summarize(text[:SUMMARY_INPUT_MAX_CHARS]), note_source="body"
    )


def _resolve_page(entry: dict, fetcher: PageFetcher, summarizer: Summarizer) -> ResolvedNote:
    """Re-fetch a page and resolve via body -> og/meta -> title (spec §7.3 ladder)."""
    # Check if client-scraped content was temporarily persisted first.
    body = (entry.get("content") or "").strip()
    if body:
        return ResolvedNote(
            note=summarizer.summarize(body[:SUMMARY_INPUT_MAX_CHARS]), note_source="body"
        )

    # fallback to re-fetch:
    page = fetcher.fetch(entry["url"])

    body = (page.body_text or "").strip()
    if body:
        # Summarize a bounded prefix (routing-card note, spec §7.3); the page body is
        # re-fetchable via the URL, so nothing is lost by reading only the prefix here.
        return ResolvedNote(
            note=summarizer.summarize(body[:SUMMARY_INPUT_MAX_CHARS]), note_source="body"
        )

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
