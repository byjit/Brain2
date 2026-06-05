"""Conservative tag normalization (spec §7.2).

Lowercase / trim / strip surrounding punctuation, and collapse plurals ONLY via a safe
rule guarded by a tech-term stoplist — never blind-stem. These are pure-function tests,
no DB or providers.
"""

import pytest

from brain2.services.canonicalize import normalize_tag


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Python", "python"),
        ("  Rust  ", "rust"),
        ("#golang", "golang"),
        ("(async)", "async"),
        ("Machine Learning", "machine learning"),
    ],
)
def test_lowercase_trim_strip_punctuation(raw, expected):
    assert normalize_tag(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("tutorials", "tutorial"),  # safe plural collapse
        ("libraries", "library"),   # -ies -> -y
        ("databases", "database"),
    ],
)
def test_safe_plural_collapse(raw, expected):
    assert normalize_tag(raw) == expected


@pytest.mark.parametrize(
    "term",
    ["redis", "kubernetes", "kafka", "nginx", "css", "ios", "js"],
)
def test_tech_term_stoplist_never_mangled(term):
    # The whole point: 'redis' must NOT become 'redi', 'kubernetes' not 'kubernete'.
    assert normalize_tag(term) == term


def test_short_token_not_stemmed():
    # Too short to safely strip a trailing 's'.
    assert normalize_tag("os") == "os"


def test_empty_and_whitespace():
    assert normalize_tag("   ") == ""
    assert normalize_tag("") == ""
