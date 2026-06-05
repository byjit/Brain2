"""Unit tests for the pure URL normalization service (spec §7.1 step 1)."""

import pytest

from brain2.services.url_normalize import normalize_url


def test_strips_utm_and_tracking_params():
    url = "https://example.com/path?utm_source=x&utm_medium=y&gclid=abc&fbclid=def&ref=twitter&id=42"
    # Only the non-tracking param survives.
    assert normalize_url(url) == "https://example.com/path?id=42"


def test_strips_trailing_slash():
    assert normalize_url("https://example.com/path/") == "https://example.com/path"


def test_root_path_keeps_single_slash():
    # The root path normalizes to a bare host with a slash (not stripped to nothing).
    assert normalize_url("https://example.com/") == "https://example.com/"


def test_lowercases_scheme_and_host():
    assert normalize_url("HTTPS://Example.COM/Path") == "https://example.com/Path"


def test_drops_fragment():
    assert normalize_url("https://example.com/path#section") == "https://example.com/path"


def test_removes_query_entirely_when_only_tracking_params():
    assert normalize_url("https://example.com/p?utm_source=x&fbclid=y") == "https://example.com/p"


def test_preserves_meaningful_query_order_independent():
    # Remaining params are sorted for stable dedup keys.
    assert normalize_url("https://example.com/p?b=2&a=1") == "https://example.com/p?a=1&b=2"


def test_combined_normalization():
    raw = "HTTPS://Example.com/Article/?utm_campaign=spring&page=2#top"
    assert normalize_url(raw) == "https://example.com/Article?page=2"


@pytest.mark.parametrize("falsy", [None, "", "   "])
def test_empty_returns_none(falsy):
    assert normalize_url(falsy) is None
