"""Tests for the note-source fallback ladder resolver (spec §7.3).

Ladder: parsed body -> og:description / meta -> title. Short-circuits: a note's text
IS the note (no LLM); a clip < ~400 chars IS the note (no LLM); otherwise summarize.
All tests run offline using the fake providers.
"""

from brain2.services.note_resolver import ResolvedNote, resolve_note
from brain2.services.providers.page_fetcher import FakePageFetcher, PageContent
from brain2.services.providers.summarizer import FakeSummarizer


def _entry(**overrides):
    """A minimal entry-row dict for the resolver."""
    base = {
        "type": "page",
        "url": "https://example.com/a",
        "title": None,
        "content": None,
    }
    base.update(overrides)
    return base


# --- page: re-fetch + ladder ------------------------------------------------


def test_page_body_summarized_note_source_body():
    fetcher = FakePageFetcher(
        default=PageContent(body_text="A long article body. " * 50, title="T", og_description="og")
    )
    summarizer = FakeSummarizer()
    result = resolve_note(_entry(), fetcher=fetcher, summarizer=summarizer)
    assert result.note_source == "body"
    assert result.note.startswith("Summary:")
    assert fetcher.calls == ["https://example.com/a"]  # page bodies are re-fetched
    assert len(summarizer.calls) == 1


def test_page_og_fallback_when_body_empty():
    fetcher = FakePageFetcher(
        default=PageContent(body_text=None, og_description="The publisher teaser copy.", title="T")
    )
    summarizer = FakeSummarizer()
    result = resolve_note(_entry(), fetcher=fetcher, summarizer=summarizer)
    assert result.note_source == "og"
    # og/meta is short teaser copy -> taken verbatim, not summarized.
    assert result.note == "The publisher teaser copy."
    assert summarizer.calls == []


def test_page_title_fallback_when_body_and_og_empty():
    fetcher = FakePageFetcher(default=PageContent(body_text=None, og_description=None, title="Just a Title"))
    summarizer = FakeSummarizer()
    result = resolve_note(_entry(), fetcher=fetcher, summarizer=summarizer)
    assert result.note_source == "title"
    assert result.note == "Just a Title"
    assert summarizer.calls == []


def test_page_uses_stored_title_when_extraction_empty():
    # Nothing extractable at all -> fall back to the entry's own stored title.
    fetcher = FakePageFetcher(default=PageContent())
    summarizer = FakeSummarizer()
    result = resolve_note(_entry(title="Stored Title"), fetcher=fetcher, summarizer=summarizer)
    assert result.note_source == "title"
    assert result.note == "Stored Title"


# --- note: user text is the note, no LLM ------------------------------------


def test_note_keeps_user_text_no_summarizer():
    summarizer = FakeSummarizer()
    fetcher = FakePageFetcher()
    entry = _entry(type="note", url=None, content="my own thoughts on the matter")
    result = resolve_note(entry, fetcher=fetcher, summarizer=summarizer)
    assert result.note == "my own thoughts on the matter"
    assert result.note_source == "user"
    assert summarizer.calls == []
    assert fetcher.calls == []  # notes are never re-fetched


# --- clip: short verbatim, long summarized ----------------------------------


def test_short_clip_is_note_verbatim_no_summarizer():
    summarizer = FakeSummarizer()
    fetcher = FakePageFetcher()
    short = "a brief highlighted snippet"
    entry = _entry(type="clip", content=short)
    result = resolve_note(entry, fetcher=fetcher, summarizer=summarizer)
    assert result.note == short
    assert result.note_source == "body"
    assert summarizer.calls == []
    assert fetcher.calls == []  # clip content is persisted, not re-fetched


def test_long_clip_is_summarized():
    summarizer = FakeSummarizer()
    fetcher = FakePageFetcher()
    long_clip = "word " * 200  # well over the ~400-char short-circuit
    entry = _entry(type="clip", content=long_clip)
    result = resolve_note(entry, fetcher=fetcher, summarizer=summarizer)
    assert result.note_source == "body"
    assert result.note.startswith("Summary:")
    assert len(summarizer.calls) == 1
    assert fetcher.calls == []


def test_resolved_note_is_dataclass():
    assert ResolvedNote(note="x", note_source="body").note == "x"
