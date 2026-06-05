"""Page fetcher provider interface + implementations (spec §7.3).

``page`` entries do not persist their body (it is re-fetchable via URL), so the worker
re-fetches and extracts at processing time. The worker depends on the ``PageFetcher``
abstraction; tests use ``FakePageFetcher`` with canned fields and never hit the network.
The real ``HttpxPageFetcher`` fetches with httpx and extracts with trafilatura.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class PageContent:
    """The extracted pieces of a page, in note-source ladder order (spec §7.3).

    Any field may be empty/None; the resolver walks body -> og/meta -> title.
    """

    body_text: str | None = None
    og_description: str | None = None
    meta_description: str | None = None
    title: str | None = None


@runtime_checkable
class PageFetcher(Protocol):
    """Fetches a URL and extracts the note-basis fields."""

    def fetch(self, url: str) -> PageContent:
        """Fetch ``url`` and return its extracted :class:`PageContent`."""
        ...


class FakePageFetcher:
    """Offline fetcher returning canned content, keyed by URL.

    A ``default`` is returned for any URL not explicitly mapped. Records fetched URLs
    so tests can assert the worker re-fetched a page rather than using stored content.
    """

    def __init__(
        self,
        pages: dict[str, PageContent] | None = None,
        *,
        default: PageContent | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._pages = pages or {}
        self._default = default or PageContent()
        self._raises = raises
        self.calls: list[str] = []

    def fetch(self, url: str) -> PageContent:
        self.calls.append(url)
        if self._raises is not None:
            raise self._raises
        return self._pages.get(url, self._default)


class HttpxPageFetcher:
    """Real fetcher: httpx GET + trafilatura body/metadata extraction."""

    def __init__(self, *, timeout: float = 10.0) -> None:
        self._timeout = timeout

    def fetch(self, url: str) -> PageContent:
        import httpx
        import trafilatura

        with httpx.Client(timeout=self._timeout, follow_redirects=True) as http:
            response = http.get(url)
            # A 404/403/500 (or a redirect to a login/consent wall) must not be extracted
            # and stored as the note; raise so it routes through the worker's retry/fail
            # path with an actionable error_message instead of silently persisting it.
            response.raise_for_status()
            html = response.text

        body = trafilatura.extract(html) or None
        metadata = trafilatura.extract_metadata(html)
        # trafilatura folds og:description and <meta name="description"> into a single
        # `description` field (preferring og), which is exactly the spec's combined
        # "og:description / meta" rung; surface it as og_description.
        og_description = getattr(metadata, "description", None) if metadata else None
        title = getattr(metadata, "title", None) if metadata else None
        return PageContent(
            body_text=body,
            og_description=og_description,
            meta_description=None,
            title=title,
        )
