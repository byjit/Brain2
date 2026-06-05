"""Tagger provider — the SINGLE combined Gemini structured-output call (spec §7.2).

Offline with FakeTagger (deterministic, call-recording). Asserts the request shape (basis
text + structured-source tags + nearest existing tags) and the output shape (note +
candidate tags + per-NEW-tag descriptions). The "exactly one call per entry" assertion
lives in the tagging-pipeline tests; here we exercise the provider contract itself.
"""

import types

import pytest

from brain2.services.providers.tagger import (
    FakeTagger,
    GeminiTagger,
    TagProposal,
    TagRequest,
)


def test_fake_tagger_records_request_and_returns_proposal():
    tagger = FakeTagger(
        result=TagProposal(
            note="A fast async HTTP client for Python.",
            tags=["python", "http", "async"],
            new_tag_descriptions={"http": "HTTP networking clients and servers"},
        )
    )
    req = TagRequest(
        basis_text="httpx is a fully featured HTTP client for Python 3.",
        structured_tags=["python", "http"],
        nearest_existing_tags=["python", "async"],
        needs_summary=True,
    )

    result = tagger.propose(req)

    assert len(tagger.calls) == 1
    assert tagger.calls[0] is req
    assert result.note == "A fast async HTTP client for Python."
    assert result.tags == ["python", "http", "async"]
    assert result.new_tag_descriptions["http"] == "HTTP networking clients and servers"


def test_fake_tagger_default_is_deterministic():
    tagger = FakeTagger()
    req = TagRequest(
        basis_text="Rust systems programming",
        structured_tags=["rust"],
        nearest_existing_tags=[],
        needs_summary=False,
    )
    result = tagger.propose(req)
    # Default fake echoes the structured tags as candidates and mints a description each.
    assert "rust" in result.tags
    assert "rust" in result.new_tag_descriptions


def test_gemini_tagger_raises_actionable_error_on_unparseable_output():
    """When the SDK can't coerce the response to the schema (response.parsed is None),
    GeminiTagger must raise a clear ValueError so the worker's failure carries an actionable
    message — not a cryptic AttributeError on None."""
    # Build the instance without the keyed constructor, then inject a stub client whose
    # response.parsed is None (the SDK's unparseable-output signal).
    tagger = GeminiTagger.__new__(GeminiTagger)
    tagger._model = "stub"
    tagger._min_tags = 3
    tagger._max_tags = 5
    tagger._types = types.SimpleNamespace(
        GenerateContentConfig=lambda **_: None
    )

    class _StubModels:
        def generate_content(self, **_):
            return types.SimpleNamespace(parsed=None)

    tagger._client = types.SimpleNamespace(models=_StubModels())

    req = TagRequest(
        basis_text="x", structured_tags=[], nearest_existing_tags=[], needs_summary=False
    )
    with pytest.raises(ValueError, match="unparseable"):
        tagger.propose(req)
