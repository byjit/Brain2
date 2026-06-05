"""Tests for provider DI wiring (spec §7: external services behind fakes).

When no GEMINI_API_KEY is configured, the factory returns fake providers so the worker
runs fully offline; when a key is present it builds the real Gemini-backed providers.
No network/Gemini calls are made here — we only assert which type is wired.
"""

from brain2.config import Settings
from brain2.services.providers.embedder import FakeEmbedder, GeminiEmbedder
from brain2.services.providers.factory import build_providers, build_tagging_providers
from brain2.services.providers.page_fetcher import FakePageFetcher, HttpxPageFetcher
from brain2.services.providers.summarizer import FakeSummarizer, GeminiSummarizer
from brain2.services.providers.tagger import FakeTagger, GeminiTagger
from brain2.services.structured_tags import FakeStructuredTagSource, HttpxStructuredTagSource


def test_no_api_key_yields_fakes():
    settings = Settings(gemini_api_key=None)
    summarizer, fetcher, embedder = build_providers(settings)
    assert isinstance(summarizer, FakeSummarizer)
    assert isinstance(fetcher, FakePageFetcher)
    assert isinstance(embedder, FakeEmbedder)


def test_api_key_yields_real_providers():
    settings = Settings(gemini_api_key="fake-key-for-wiring", gemini_summary_model="gemini-3.5-flash")
    summarizer, fetcher, embedder = build_providers(settings)
    assert isinstance(summarizer, GeminiSummarizer)
    assert isinstance(fetcher, HttpxPageFetcher)
    assert isinstance(embedder, GeminiEmbedder)


def test_no_api_key_yields_fake_tagging_providers():
    tagger, source = build_tagging_providers(Settings(gemini_api_key=None))
    assert isinstance(tagger, FakeTagger)
    assert isinstance(source, FakeStructuredTagSource)


def test_api_key_yields_real_tagging_providers():
    settings = Settings(gemini_api_key="fake-key-for-wiring", gemini_summary_model="gemini-3.5-flash")
    tagger, source = build_tagging_providers(settings)
    assert isinstance(tagger, GeminiTagger)
    assert isinstance(source, HttpxStructuredTagSource)
