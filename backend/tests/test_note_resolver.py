"""Tests for the note-source fallback ladder resolver (spec §7.3).

Ladder: parsed body -> og:description / meta -> title. Short-circuits: a note's text
IS the note (no LLM); a clip < ~400 chars IS the note (no LLM); otherwise summarize.
All tests run offline using the fake providers.
"""

from brain2.services.note_resolver import (
    ResolvedNote,
    is_code_dominant,
    resolve_basis,
    resolve_note,
)
from brain2.services.providers.page_fetcher import FakePageFetcher, PageContent
from brain2.services.providers.summarizer import SUMMARY_INPUT_MAX_CHARS, FakeSummarizer


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


def test_long_body_summarized_from_bounded_prefix():
    """A body larger than the summary window is summarized from a bounded prefix (spec §7.3).

    The note is a routing card and the full text stays re-fetchable / FTS-indexed, so the
    summarizer never receives more than SUMMARY_INPUT_MAX_CHARS — capping LLM cost/latency.
    """
    huge_body = "word " * (SUMMARY_INPUT_MAX_CHARS)  # ~5x the window in chars
    fetcher = FakePageFetcher(default=PageContent(body_text=huge_body, title="T"))
    summarizer = FakeSummarizer()

    resolve_note(_entry(), fetcher=fetcher, summarizer=summarizer)

    assert len(summarizer.calls) == 1
    assert len(summarizer.calls[0]) == SUMMARY_INPUT_MAX_CHARS


def test_resolved_note_is_dataclass():
    assert ResolvedNote(note="x", note_source="body").note == "x"


# --- clip: code-dominant short clips are captioned, not verbatim -------------
# A raw code snippet embeds poorly for paraphrase search, so a code-dominant short
# clip takes the summarize path (a descriptive caption) instead of short-circuiting to
# verbatim. The verbatim code stays safe in `content`. Scope is `clip` ONLY.


def test_short_code_clip_with_fence_needs_summary():
    # A fenced code block is unambiguous code -> summarize path, note not yet set.
    fenced = "```js\nconst x = debounce(fn, 200);\n```"
    basis = resolve_basis(_entry(type="clip", content=fenced), fetcher=FakePageFetcher())
    assert basis.needs_summary is True
    assert basis.note_source == "body"
    assert basis.note == ""  # produced downstream by the tagger
    assert basis.text == fenced  # the verbatim clip is still embedded/basis


def test_short_code_clip_without_fence_needs_summary():
    # Several lines of clearly-code JS (no fence) -> still the summarize path.
    code = (
        "function debounce(fn, wait) {\n"
        "  let t;\n"
        "  return (...args) => {\n"
        "    clearTimeout(t);\n"
        "    t = setTimeout(() => fn(...args), wait);\n"
        "  };\n"
        "}"
    )
    basis = resolve_basis(_entry(type="clip", content=code), fetcher=FakePageFetcher())
    assert basis.needs_summary is True
    assert basis.note_source == "body"
    assert basis.note == ""


def test_short_prose_clip_stays_verbatim():
    prose = "a brief highlighted snippet of ordinary prose"
    basis = resolve_basis(_entry(type="clip", content=prose), fetcher=FakePageFetcher())
    assert basis.needs_summary is False
    assert basis.note_source == "body"
    assert basis.note == prose
    assert basis.text == prose


def test_short_prose_with_inline_code_token_stays_verbatim():
    # Ordinary prose that merely mentions an identifier must NOT be treated as code.
    prose = "Use the useEffect() hook here to clean up the timer when done."
    basis = resolve_basis(_entry(type="clip", content=prose), fetcher=FakePageFetcher())
    assert basis.needs_summary is False
    assert basis.note == prose


def test_short_code_conversation_stays_verbatim():
    # The code-dominant exception is scoped to `clip` only; conversation is unchanged.
    code = "```js\nconst x = debounce(fn, 200);\n```"
    basis = resolve_basis(_entry(type="conversation", content=code), fetcher=FakePageFetcher())
    assert basis.needs_summary is False
    assert basis.note == code


def test_short_code_clip_resolve_note_calls_summarizer():
    # resolve_note mirrors resolve_basis: a short code clip is summarized (captioned).
    summarizer = FakeSummarizer()
    fenced = "```py\nx = [i for i in range(10) if i % 2 == 0]\n```"
    result = resolve_note(
        _entry(type="clip", content=fenced), fetcher=FakePageFetcher(), summarizer=summarizer
    )
    assert result.note_source == "body"
    assert result.note.startswith("Summary:")
    assert len(summarizer.calls) == 1


def test_short_prose_clip_resolve_note_stays_verbatim():
    summarizer = FakeSummarizer()
    prose = "a brief highlighted snippet"
    result = resolve_note(
        _entry(type="clip", content=prose), fetcher=FakePageFetcher(), summarizer=summarizer
    )
    assert result.note == prose
    assert summarizer.calls == []


# --- is_code_dominant heuristic: direct unit tests --------------------------


def test_is_code_dominant_empty_is_false():
    assert is_code_dominant("") is False
    assert is_code_dominant("   \n\t  ") is False


def test_is_code_dominant_prose_is_false():
    assert is_code_dominant("This is a perfectly ordinary sentence of prose.") is False


def test_is_code_dominant_prose_with_inline_token_is_false():
    assert is_code_dominant("Call the render() method when the component mounts.") is False


def test_is_code_dominant_fenced_block_is_true():
    assert is_code_dominant("```\nconst x = 1;\n```") is True


def test_is_code_dominant_unfenced_code_is_true():
    code = (
        "const t = setTimeout(() => fn(), wait);\n"
        "clearTimeout(t);\n"
        "return { done: true };"
    )
    assert is_code_dominant(code) is True
