"""Structured-source tag priors (spec §7.2 mechanism 1).

High-confidence tags from real metadata BEFORE inference: OG/meta keywords from the
already-fetched page, and GitHub repo topics + primary language. Offline with the fake.
"""

import pytest

from brain2.services.providers.page_fetcher import PageContent
from brain2.services.structured_tags import (
    FakeStructuredTagSource,
    extract_keyword_tags,
    parse_github_repo,
)


def test_extract_keyword_tags_from_og_meta():
    # OG/meta keywords pulled straight off the already-fetched page.
    page = PageContent(
        body_text="...",
        og_description="A guide",
        title="Guide",
        meta_description=None,
        keywords=["Python, Web Development, FastAPI"],
    )
    tags = extract_keyword_tags(page)
    assert tags == ["python", "web development", "fastapi"]


def test_extract_keyword_tags_empty_when_none():
    assert extract_keyword_tags(PageContent()) == []


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/encode/httpx", ("encode", "httpx")),
        ("https://github.com/encode/httpx/", ("encode", "httpx")),
        ("https://github.com/encode/httpx/blob/master/README.md", ("encode", "httpx")),
        ("https://example.com/encode/httpx", None),
        ("not a url", None),
    ],
)
def test_parse_github_repo(url, expected):
    assert parse_github_repo(url) == expected


def test_fake_source_returns_github_topics_and_language():
    source = FakeStructuredTagSource(
        repos={
            "encode/httpx": {
                "topics": ["http", "async", "python"],
                "language": "Python",
            }
        }
    )
    tags = source.priors(
        url="https://github.com/encode/httpx",
        page=PageContent(),
    )
    # topics + detected language, normalized to lowercase prior tags.
    assert "http" in tags
    assert "async" in tags
    assert "python" in tags


def test_fake_source_merges_og_keywords_and_github(monkeypatch):
    source = FakeStructuredTagSource(
        repos={"o/r": {"topics": ["cli"], "language": "Rust"}},
    )
    page = PageContent(title="t", keywords=["Distributed, CLI"])
    tags = source.priors(url="https://github.com/o/r", page=page)
    assert "cli" in tags
    assert "rust" in tags
    assert "distributed" in tags


def test_fake_source_tolerates_unknown_repo():
    source = FakeStructuredTagSource(repos={})
    assert source.priors(url="https://github.com/x/y", page=PageContent()) == []
