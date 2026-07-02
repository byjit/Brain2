"""Deterministic entry listing (spec §10 list).

``list_entries`` is the browse/filter complement to ``retrieve``: no search query, no
relevance ranking — just optional tag (ANY) + saved_at-range filters, newest-first,
paged. Only active entries surface.
"""

import pytest

from brain2.db.connection import open_user_db
from brain2.models.entries import CreateEntryRequest
from brain2.services.entries import list_entries, save_entry


@pytest.fixture
def conn(tmp_path):
    with open_user_db("list-user", data_dir=tmp_path) as c:
        yield c


def _save_active(conn, *, text, saved_at=None, status="active", tags=()):
    """Save a note entry and force it active (save_entry lands rows as 'pending').

    ``saved_at`` lets a test pin the ordering key deterministically rather than relying
    on the near-identical wall-clock timestamps several saves would otherwise share.
    """
    res = save_entry(conn, CreateEntryRequest(type="note", captured_text=text))
    if saved_at is not None:
        conn.execute("UPDATE entries SET saved_at = ? WHERE id = ?", (saved_at, res.id))
    conn.execute("UPDATE entries SET status = ? WHERE id = ?", (status, res.id))
    for t in tags:
        conn.execute("INSERT OR IGNORE INTO tags (name, description) VALUES (?, '')", (t,))
        conn.execute(
            "INSERT OR IGNORE INTO entry_tags (entry_id, tag) VALUES (?, ?)", (res.id, t)
        )
    conn.commit()
    return res.id


def test_orders_newest_first(conn):
    old = _save_active(conn, text="older", saved_at="2026-01-01T00:00:00Z")
    new = _save_active(conn, text="newer", saved_at="2026-06-01T00:00:00Z")
    mid = _save_active(conn, text="middle", saved_at="2026-03-01T00:00:00Z")
    assert [r["id"] for r in list_entries(conn)] == [new, mid, old]


def test_result_shape_has_no_score(conn):
    _save_active(conn, text="something")
    row = list_entries(conn)[0]
    assert set(row.keys()) == {"id", "url", "title", "tags", "note", "note_source", "content", "type", "saved_at"}
    assert "score" not in row


def test_excludes_non_active_entries(conn):
    active = _save_active(conn, text="ready", status="active")
    _save_active(conn, text="still processing", status="pending")
    _save_active(conn, text="broke", status="failed")
    assert [r["id"] for r in list_entries(conn)] == [active]


def test_tag_filter_is_any_union(conn):
    a = _save_active(conn, text="rust doc", tags=("rust",))
    b = _save_active(conn, text="python doc", tags=("python",))
    c = _save_active(conn, text="go doc", tags=("go",))
    got = {r["id"] for r in list_entries(conn, tags=["rust", "python"])}
    # ANY-match: carrying either tag qualifies; the unrelated entry is excluded.
    assert got == {a, b}
    assert c not in got


def test_saved_after_is_inclusive_lower_bound(conn):
    _save_active(conn, text="too old", saved_at="2026-01-01T00:00:00Z")
    edge = _save_active(conn, text="on the bound", saved_at="2026-03-01T00:00:00Z")
    newer = _save_active(conn, text="after", saved_at="2026-04-01T00:00:00Z")
    got = [r["id"] for r in list_entries(conn, saved_after="2026-03-01T00:00:00Z")]
    assert got == [newer, edge]


def test_saved_before_is_inclusive_upper_bound(conn):
    older = _save_active(conn, text="before", saved_at="2026-01-01T00:00:00Z")
    edge = _save_active(conn, text="on the bound", saved_at="2026-03-01T00:00:00Z")
    _save_active(conn, text="too new", saved_at="2026-04-01T00:00:00Z")
    got = [r["id"] for r in list_entries(conn, saved_before="2026-03-01T00:00:00Z")]
    assert got == [edge, older]


def test_date_range_combines_with_tag(conn):
    _save_active(conn, text="in range wrong tag", saved_at="2026-03-15T00:00:00Z", tags=("python",))
    hit = _save_active(conn, text="in range right tag", saved_at="2026-03-20T00:00:00Z", tags=("rust",))
    _save_active(conn, text="out of range right tag", saved_at="2026-05-01T00:00:00Z", tags=("rust",))
    got = [
        r["id"]
        for r in list_entries(
            conn, tags=["rust"], saved_after="2026-03-01T00:00:00Z", saved_before="2026-04-01T00:00:00Z"
        )
    ]
    assert got == [hit]


def test_limit_and_offset_paginate(conn):
    ids = [
        _save_active(conn, text=f"entry {i}", saved_at=f"2026-01-{i + 1:02d}T00:00:00Z")
        for i in range(5)
    ]
    newest_first = list(reversed(ids))
    page1 = [r["id"] for r in list_entries(conn, limit=2, offset=0)]
    page2 = [r["id"] for r in list_entries(conn, limit=2, offset=2)]
    assert page1 == newest_first[:2]
    assert page2 == newest_first[2:4]


def test_no_filters_returns_recent_entries(conn):
    a = _save_active(conn, text="one", saved_at="2026-01-01T00:00:00Z")
    b = _save_active(conn, text="two", saved_at="2026-02-01T00:00:00Z")
    assert [r["id"] for r in list_entries(conn)] == [b, a]


def test_negative_limit_raises(conn):
    with pytest.raises(ValueError, match="limit must be >= 0"):
        list_entries(conn, limit=-1)


def test_negative_offset_raises(conn):
    with pytest.raises(ValueError, match="offset must be >= 0"):
        list_entries(conn, offset=-1)
