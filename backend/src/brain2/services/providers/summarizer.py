"""Summarizer provider interface + implementations (spec §7.1 step, §7.3).

The async worker depends on the ``Summarizer`` abstraction (dependency inversion),
never on Gemini directly, so the pipeline is unit-testable offline with ``FakeSummarizer``.
The real ``GeminiSummarizer`` uses the google-genai SDK + Gemini Flash.
"""

from typing import Protocol, runtime_checkable

# Instruction kept terse and deterministic: the note is the vectorized field (spec §5),
# so we want a compact 2-3 sentence concept summary, not a verbatim copy.
_SUMMARY_INSTRUCTION = (
    "Summarize the following content into a neutral 2-3 sentence note capturing what it "
    "is about. Output only the summary, no preamble.\n\nContent:\n"
)


@runtime_checkable
class Summarizer(Protocol):
    """Turns source text into a concise 2-3 sentence note."""

    def summarize(self, text: str) -> str:
        """Return a 2-3 sentence note for ``text``."""
        ...


class FakeSummarizer:
    """Deterministic offline summarizer for tests.

    Records every call so tests can assert the worker did (or did not) summarize, and
    can be primed to raise to exercise the worker's retry/failure path.
    """

    def __init__(self, *, raises: Exception | None = None) -> None:
        self._raises = raises
        self.calls: list[str] = []

    def summarize(self, text: str) -> str:
        self.calls.append(text)
        if self._raises is not None:
            raise self._raises
        # Deterministic, content-derived so assertions are stable.
        head = " ".join(text.split()[:8])
        return f"Summary: {head}"


# Request timeout (ms) for a single summarization call. A stalled call must fail fast
# rather than wedge the shared worker drain thread for all users (spec §7.4).
_REQUEST_TIMEOUT_MS = 30_000


class GeminiSummarizer:
    """Real summarizer backed by the google-genai SDK + Gemini Flash."""

    def __init__(self, api_key: str, model: str) -> None:
        # Import lazily so the SDK is only required when the real provider is used.
        from google import genai
        from google.genai import types

        # An explicit request timeout bounds every call so a network stall fails fast
        # and routes through the worker's retry/fail path.
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=_REQUEST_TIMEOUT_MS),
        )
        self._model = model

    def summarize(self, text: str) -> str:
        response = self._client.models.generate_content(
            model=self._model,
            contents=_SUMMARY_INSTRUCTION + text,
        )
        return (response.text or "").strip()
