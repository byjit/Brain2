"""Optional live Gemini smoke test (spec §7.1 summarization).

Deselected by default: skipped unless GEMINI_API_KEY is set in the environment, so the
default offline suite never needs a key or network. Run with the key present to verify
the real GeminiSummarizer against the live API.
"""

import os

import pytest

from brain2.config import get_settings
from brain2.services.providers.summarizer import GeminiSummarizer

pytestmark = pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set; live Gemini test skipped"
)


def test_gemini_summarizer_returns_text():
    settings = get_settings()
    summarizer = GeminiSummarizer(
        api_key=settings.gemini_api_key, model=settings.gemini_summary_model
    )
    note = summarizer.summarize(
        "The Rust programming language is a systems language focused on safety, "
        "concurrency, and performance, using an ownership model instead of a garbage collector."
    )
    assert isinstance(note, str) and note.strip()
