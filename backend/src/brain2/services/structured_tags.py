"""Structured-source tag priors (spec §7.2 mechanism 1).

Before any inference, pull tags that already exist as real metadata: OG/meta keywords
from the already-fetched page, and for a ``github.com/{owner}/{repo}`` URL the repo's
topics + primary language via the public GitHub REST API. These are high-confidence and
don't fragment, so they SEED the candidate set — they are priors, not guesses.

External access (the GitHub API) sits behind the ``StructuredTagSource`` abstraction with
a deterministic fake, so every unit test runs offline. The pure helpers
(``extract_keyword_tags``, ``parse_github_repo``) are shared by both impls (DRY).
"""

import re
from typing import Protocol, runtime_checkable

from brain2.services.canonicalize import normalize_tag
from brain2.services.providers.page_fetcher import PageContent

# github.com/{owner}/{repo}[/...] — owner/repo are the first two path segments.
_GITHUB_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([^/\s]+)/([^/\s]+?)(?:/.*)?/?$", re.IGNORECASE
)
# GitHub's "special" first segments are routes, not owners (avoid false repo matches).
_GITHUB_RESERVED = frozenset({"orgs", "topics", "marketplace", "sponsors", "settings"})


def parse_github_repo(url: str | None) -> tuple[str, str] | None:
    """Return ``(owner, repo)`` for a GitHub repo URL, else None (spec §7.2)."""
    if not url:
        return None
    match = _GITHUB_RE.match(url.strip())
    if not match:
        return None
    owner, repo = match.group(1), match.group(2)
    if owner.lower() in _GITHUB_RESERVED:
        return None
    # Strip a trailing '.git' that clone URLs carry.
    repo = repo[:-4] if repo.endswith(".git") else repo
    return owner, repo


def extract_keyword_tags(page: PageContent) -> list[str]:
    """Normalize a page's meta keywords into prior tags (spec §7.2 mechanism 1).

    ``page.keywords`` is a list of meta-keyword strings (each possibly comma-separated, as
    the fetcher surfaces them). Empty/None yields no priors.
    """
    tags: list[str] = []
    for entry in page.keywords or []:
        for raw in entry.split(","):
            norm = normalize_tag(raw)
            if norm and norm not in tags:
                tags.append(norm)
    return tags


def _topics_and_language_tags(topics: list[str], language: str | None) -> list[str]:
    """Normalize GitHub topics + primary language into deduped prior tags."""
    tags: list[str] = []
    for raw in [*topics, language or ""]:
        norm = normalize_tag(raw)
        if norm and norm not in tags:
            tags.append(norm)
    return tags


@runtime_checkable
class StructuredTagSource(Protocol):
    """Yields high-confidence prior tags from a page's real metadata (spec §7.2)."""

    def priors(self, *, url: str | None, page: PageContent) -> list[str]:
        """Return prior tags for an entry; never raises (best-effort, tolerant)."""
        ...


class FakeStructuredTagSource:
    """Offline structured-tag source: canned GitHub repo metadata + OG keywords.

    ``repos`` maps ``"owner/repo"`` to ``{"topics": [...], "language": "..."}``. An
    unmapped repo (or non-GitHub URL) contributes no GitHub priors, mirroring the real
    impl's graceful 404/rate-limit handling.
    """

    def __init__(self, repos: dict[str, dict] | None = None) -> None:
        self._repos = repos or {}

    def priors(self, *, url: str | None, page: PageContent) -> list[str]:
        tags = extract_keyword_tags(page)
        repo = parse_github_repo(url)
        if repo is not None:
            meta = self._repos.get(f"{repo[0]}/{repo[1]}")
            if meta:
                for tag in _topics_and_language_tags(
                    meta.get("topics", []), meta.get("language")
                ):
                    if tag not in tags:
                        tags.append(tag)
        return tags


# Request timeout (s) for the unauthenticated GitHub API call — fail fast and tolerate.
_GITHUB_TIMEOUT_S = 5.0
_GITHUB_API = "https://api.github.com/repos/{owner}/{repo}"


class HttpxStructuredTagSource:
    """Real structured-tag source: OG keywords + unauthenticated GitHub REST API.

    The GitHub call is best-effort: a rate-limit (403), a missing repo (404), or any
    network error contributes no GitHub priors rather than failing the whole pipeline
    (spec §7.2 "tolerate rate-limit/404 gracefully").
    """

    def __init__(self, *, timeout: float = _GITHUB_TIMEOUT_S) -> None:
        self._timeout = timeout

    def priors(self, *, url: str | None, page: PageContent) -> list[str]:
        tags = extract_keyword_tags(page)
        repo = parse_github_repo(url)
        if repo is not None:
            for tag in self._github_priors(*repo):
                if tag not in tags:
                    tags.append(tag)
        return tags

    def _github_priors(self, owner: str, repo: str) -> list[str]:
        import httpx

        try:
            with httpx.Client(timeout=self._timeout, follow_redirects=True) as http:
                response = http.get(
                    _GITHUB_API.format(owner=owner, repo=repo),
                    headers={"Accept": "application/vnd.github+json"},
                )
                if response.status_code != 200:
                    return []  # 403 rate-limit / 404 not-found / etc. — tolerate
                data = response.json()
        except Exception:  # noqa: BLE001 — network errors must never fail tagging
            return []
        topics = data.get("topics") or []
        language = data.get("language")
        return _topics_and_language_tags(topics, language)
