"""URL normalization for dedup (spec §5, §7.1 step 1).

Pure function with no I/O so it stays trivially unit-testable. The normalized URL
is the dedup key; the raw URL is preserved separately as ``original_url`` by callers.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Tracking / analytics params stripped before dedup. ``utm_*`` is matched by prefix.
_TRACKING_PARAMS = frozenset(
    {
        "gclid",
        "fbclid",
        "ref",
        "ref_src",
        "ref_url",
        "mc_cid",
        "mc_eid",
        "igshid",
        "yclid",
        "msclkid",
        "_hsenc",
        "_hsmi",
    }
)


def _is_tracking_param(key: str) -> bool:
    """A query key is tracking if it starts with ``utm_`` or is in the stoplist."""
    lowered = key.lower()
    return lowered.startswith("utm_") or lowered in _TRACKING_PARAMS


def normalize_url(url: str | None) -> str | None:
    """Return a canonical URL for dedup, or ``None`` for empty input.

    Normalization rules:
    - lowercase scheme and host
    - drop the fragment
    - strip ``utm_*`` and common tracking params
    - sort remaining query params for a stable key
    - strip a trailing slash from non-root paths
    """
    if not url or not url.strip():
        return None

    parts = urlsplit(url.strip())

    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()

    # Keep only non-tracking query params, sorted for a stable dedup key.
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _is_tracking_param(k)]
    query = urlencode(sorted(kept))

    # Strip a trailing slash from non-root paths; preserve the root "/".
    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Fragment dropped by passing an empty string.
    return urlunsplit((scheme, netloc, path, query, ""))
