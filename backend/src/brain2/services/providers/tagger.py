"""Tagger/Enricher provider — the SINGLE combined Gemini call (spec §7.2, §7.1 step 6).

Exactly ONE LLM call per entry produces, together:

- the ``note`` (a 2-3 sentence summary) — only when summarization is needed; for the
  verbatim note/short-clip cases the note is already set, so the call returns tags only;
- the ``tags`` candidate list — grounded by the structured-source priors and the nearest
  EXISTING tags, with an instruction to REUSE existing tags and only invent when nothing
  fits (the biggest anti-fragmentation lever);
- a concept-level ``description`` for each NEW (non-existing) candidate, embedded later by
  canonicalize-on-write.

The worker depends on the ``Tagger`` abstraction; ``FakeTagger`` makes the whole tagging
pipeline unit-testable offline. ``GeminiTagger`` uses google-genai structured output
(``response_schema`` + ``response_mime_type='application/json'``) so the model returns a
parseable object in one round trip.
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class TagRequest:
    """Input to the single combined call (spec §7.1 step 6)."""

    basis_text: str
    structured_tags: list[str]
    nearest_existing_tags: list[str]
    # When True the model must produce a summary note; when False the note is already
    # resolved (verbatim note / short clip) and only tags are wanted.
    needs_summary: bool


@dataclass(frozen=True)
class TagProposal:
    """Output of the single combined call (spec §7.1 step 6).

    ``note`` is empty when ``needs_summary`` was False. ``new_tag_descriptions`` maps a
    candidate tag name -> its concept description, present only for NEW (non-existing)
    candidates; reused existing tags need no description (it stays stable, spec §9.3).
    """

    note: str
    tags: list[str]
    new_tag_descriptions: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class Tagger(Protocol):
    """Produces the note (if needed) + candidate tags + new-tag descriptions in one call."""

    def propose(self, request: TagRequest) -> TagProposal:
        """Run the single combined enrichment call."""
        ...


class FakeTagger:
    """Deterministic offline tagger; records calls so tests assert exactly-one-call.

    With an explicit ``result`` it returns that proposal verbatim. Otherwise it echoes the
    structured-source tags as candidates and synthesizes a description for each, which is
    enough to drive the canonicalize/persist pipeline offline.
    """

    def __init__(self, *, result: TagProposal | None = None) -> None:
        self._result = result
        self.calls: list[TagRequest] = []

    def propose(self, request: TagRequest) -> TagProposal:
        self.calls.append(request)
        if self._result is not None:
            return self._result
        tags = list(dict.fromkeys(request.structured_tags))  # dedup, keep order
        descriptions = {t: f"Concept: {t}" for t in tags}
        note = f"Summary: {' '.join(request.basis_text.split()[:8])}" if request.needs_summary else ""
        return TagProposal(note=note, tags=tags, new_tag_descriptions=descriptions)


# --- Real Gemini implementation (structured output) -------------------------------------

# Structured-output schema for the single combined call. Gemini returns JSON matching this
# shape; we parse it into a TagProposal. ``new_tag_descriptions`` is a list of name/desc
# pairs rather than a free-form dict so the schema is concrete (Gemini schemas don't model
# arbitrary-key objects well).
class _NewTagDescription(BaseModel):
    name: str = Field(description="The new candidate tag name")
    description: str = Field(description="A stable concept-level description of the tag")


class _TaggerOutput(BaseModel):
    note: str = Field(
        default="",
        description="2-3 sentence summary note; empty if no summary was requested",
    )
    tags: list[str] = Field(description="3-5 candidate tags, reusing existing ones if they fit")
    new_tag_descriptions: list[_NewTagDescription] = Field(
        default_factory=list,
        description="One entry per NEW (non-existing) tag with its concept description",
    )


def _build_prompt(request: TagRequest, *, min_tags: int, max_tags: int) -> str:
    """Compose the single-call prompt with the anti-fragmentation instruction (spec §7.2)."""
    existing = ", ".join(request.nearest_existing_tags) or "(none yet)"
    priors = ", ".join(request.structured_tags) or "(none)"
    summary_clause = (
        "First write a neutral 2-3 sentence summary note of the content in `note`. "
        if request.needs_summary
        else "Leave `note` empty (the note is already set). "
    )
    return (
        f"{summary_clause}"
        f"Then choose {min_tags}-{max_tags} concise lowercase tags for the content.\n\n"
        f"Existing related tags in this library: {existing}.\n"
        f"REUSE these existing tags whenever they fit; only invent a new tag when nothing "
        f"matches. High-confidence metadata tags to consider: {priors}.\n"
        f"For every tag you invent that is NOT in the existing list, add an entry to "
        f"`new_tag_descriptions` with a stable concept-level description of that tag "
        f"(describe the concept, not this one item).\n\n"
        f"Content:\n{request.basis_text}"
    )


_REQUEST_TIMEOUT_MS = 30_000


class GeminiTagger:
    """Real tagger backed by google-genai structured output (one call per entry)."""

    def __init__(self, api_key: str, model: str, *, min_tags: int, max_tags: int) -> None:
        from google import genai
        from google.genai import types

        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=_REQUEST_TIMEOUT_MS),
        )
        self._types = types
        self._model = model
        self._min_tags = min_tags
        self._max_tags = max_tags

    def propose(self, request: TagRequest) -> TagProposal:
        response = self._client.models.generate_content(
            model=self._model,
            contents=_build_prompt(request, min_tags=self._min_tags, max_tags=self._max_tags),
            config=self._types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_TaggerOutput,
            ),
        )
        parsed: _TaggerOutput | None = response.parsed
        if parsed is None:
            # The SDK returns None when the response can't be coerced to the schema; surface
            # an actionable error (mirroring GeminiSummarizer's defensive guard) so the
            # worker's retry/fail path carries a clear message instead of an AttributeError.
            raise ValueError("tagger returned unparseable output")
        return TagProposal(
            note=(parsed.note or "").strip(),
            tags=list(parsed.tags),
            new_tag_descriptions={d.name: d.description for d in parsed.new_tag_descriptions},
        )
