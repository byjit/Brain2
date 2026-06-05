"""Provider dependency-injection wiring (spec §7).

Selects real (Gemini-backed) providers when a ``GEMINI_API_KEY`` is configured, and
deterministic fakes otherwise — so the async worker runs offline in dev/CI without
keys, and uses live services in production by configuration alone.
"""

from brain2.config import Settings
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


def build_providers(settings: Settings) -> tuple[Summarizer, PageFetcher]:
    """Return ``(summarizer, page_fetcher)`` wired from config.

    Real providers require ``gemini_api_key``; without it, fakes are returned so the
    pipeline stays runnable and tests never hit the network or Gemini.
    """
    if settings.gemini_api_key:
        summarizer: Summarizer = GeminiSummarizer(
            api_key=settings.gemini_api_key, model=settings.gemini_summary_model
        )
        fetcher: PageFetcher = HttpxPageFetcher()
        return summarizer, fetcher
    return FakeSummarizer(), FakePageFetcher()
