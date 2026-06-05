"""Tests for the conditional content-persistence rule (spec §7.3)."""

import pytest

from brain2.services.content import persisted_content, persists_content


@pytest.mark.parametrize("entry_type", ["clip", "conversation", "note"])
def test_re_fetchable_types_persist_content(entry_type):
    assert persists_content(entry_type) is True
    assert persisted_content(entry_type, "the captured text") == "the captured text"


def test_page_type_discards_content():
    # page is re-fetchable via URL -> content is NULL.
    assert persists_content("page") is False
    assert persisted_content("page", "some scraped body") is None


def test_persisted_content_handles_missing_text():
    assert persisted_content("note", None) is None
