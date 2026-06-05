"""Provider dependency-injection wiring (spec §7).

Selects real (Gemini-backed) providers when a ``GEMINI_API_KEY`` is configured, and
deterministic fakes otherwise — so the async worker runs offline in dev/CI without
keys, and uses live services in production by configuration alone.
"""

from brain2.config import Settings
from brain2.services.providers.embedder import Embedder, FakeEmbedder, GeminiEmbedder
from brain2.services.providers.page_fetcher import (
    FakePageFetcher,
    HttpxPageFetcher,
    PageFetcher,
)
from brain2.services.providers.summarizer import (
    FakeSummarizer,
    GeminiSummarizer,
    Summarizer,
)
from brain2.services.providers.tagger import FakeTagger, GeminiTagger, Tagger
from brain2.services.structured_tags import (
    FakeStructuredTagSource,
    HttpxStructuredTagSource,
    StructuredTagSource,
)


def build_providers(settings: Settings) -> tuple[Summarizer, PageFetcher, Embedder]:
    """Return ``(summarizer, page_fetcher, embedder)`` wired from config.

    Real providers require ``gemini_api_key``; without it, fakes are returned so the
    pipeline stays runnable and tests never hit the network or Gemini.
    """
    if settings.gemini_api_key:
        summarizer: Summarizer = GeminiSummarizer(
            api_key=settings.gemini_api_key, model=settings.gemini_summary_model
        )
        fetcher: PageFetcher = HttpxPageFetcher()
        embedder: Embedder = GeminiEmbedder(
            api_key=settings.gemini_api_key, model=settings.gemini_embedding_model
        )
        return summarizer, fetcher, embedder
    return FakeSummarizer(), FakePageFetcher(), FakeEmbedder()


def build_tagging_providers(settings: Settings) -> tuple[Tagger, StructuredTagSource]:
    """Return ``(tagger, structured_source)`` for the M5 auto-tagging path (spec §7.2).

    Kept separate from :func:`build_providers` so its 3-tuple contract (summarizer,
    fetcher, embedder) stays stable. Real providers require ``gemini_api_key``; without
    it, fakes are returned so the worker tags offline without keys or network.
    """
    if settings.gemini_api_key:
        tagger: Tagger = GeminiTagger(
            api_key=settings.gemini_api_key,
            model=settings.gemini_summary_model,
            min_tags=settings.tags_per_entry_min,
            max_tags=settings.tags_per_entry_max,
        )
        source: StructuredTagSource = HttpxStructuredTagSource()
        return tagger, source
    return FakeTagger(), FakeStructuredTagSource()
