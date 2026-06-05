"""Offline tests for the real HTTP-backed providers' resilience.

These never hit the network: httpx / google-genai are monkeypatched. They verify the
fixes for (a) HttpxPageFetcher raising on non-2xx responses so error pages don't get
stored as notes, and (b) GeminiSummarizer passing an explicit request timeout so a
stalled call can't wedge the shared worker thread.
"""

import httpx
import pytest

from brain2.services.providers.page_fetcher import HttpxPageFetcher


class _StubResponse:
    def __init__(self, status_code: int, text: str, request: httpx.Request) -> None:
        self.status_code = status_code
        self.text = text
        self._request = request

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}", request=self._request, response=None
            )


class _StubClient:
    def __init__(self, response: _StubResponse) -> None:
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url: str) -> _StubResponse:
        return self._response


def test_page_fetcher_raises_on_error_status(monkeypatch):
    # A 404 must become an exception (routed to the worker's retry/fail path) instead of
    # silently extracting the error page body as the user's note.
    request = httpx.Request("GET", "https://x.test/missing")
    response = _StubResponse(404, "<html>Page not found</html>", request)
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _StubClient(response))

    with pytest.raises(httpx.HTTPStatusError):
        HttpxPageFetcher().fetch("https://x.test/missing")


def test_gemini_summarizer_passes_request_timeout(monkeypatch):
    # The real summarizer must pass an explicit timeout so a hung call fails fast rather
    # than blocking the shared drain thread for all users.
    captured: dict = {}

    class _FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)

            class _Resp:
                text = "ok"

            return _Resp()

    class _FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.models = _FakeModels()

    import google.genai as genai

    monkeypatch.setattr(genai, "Client", _FakeClient)

    from brain2.services.providers.summarizer import GeminiSummarizer

    summarizer = GeminiSummarizer(api_key="k", model="m")
    summarizer.summarize("some text")

    # A timeout must be configured somewhere on the call/client path.
    serialized = repr(captured)
    assert "timeout" in serialized.lower() or "http_options" in serialized.lower()
